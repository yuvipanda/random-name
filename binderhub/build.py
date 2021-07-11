"""
Contains build of a docker image from a git repository.
"""

from collections import defaultdict
import datetime
import json
import threading
from typing import Union
from urllib.parse import urlparse
from enum import Enum
import warnings

from kubernetes import client, watch
from tornado.ioloop import IOLoop
from tornado.log import app_log

from .utils import rendezvous_rank, KUBE_REQUEST_TIMEOUT


class ProgressEvent:
    """
    Represents an event that happened in the build process
    """
    class Kind(Enum):
        """
        The kind of event that happened
        """
        BUILD_STATUS_CHANGE = 1
        LOG_MESSAGE = 2

    class BuildStatus(Enum):
        """
        The state the build is now in

        Used when `kind` is `Kind.BUILD_STATUS_CHANGE`
        """
        PENDING = 1
        RUNNING = 2
        COMPLETED = 3
        FAILED = 4
        UNKNOWN = 5

    def __init__(self, kind: Kind, payload: Union[str, BuildStatus]):
        self.kind = kind
        self.payload = payload

class Build:
    """Represents a build of a git repository into a docker image.

    This ultimately maps to a single pod on a kubernetes cluster. Many
    different build objects can point to this single pod and perform
    operations on the pod. The code in this class needs to be careful and take
    this into account.

    For example, operations a Build object tries might not succeed because
    another Build object pointing to the same pod might have done something
    else. This should be handled gracefully, and the build object should
    reflect the state of the pod as quickly as possible.

    ``name``
        The ``name`` should be unique and immutable since it is used to
        sync to the pod. The ``name`` should be unique for a
        ``(repo_url, ref)`` tuple, and the same tuple should correspond
        to the same ``name``. This allows use of the locking provided by k8s
        API instead of having to invent our own locking code.

    """

    def __init__(
        self,
        q,
        api,
        name,
        *,
        namespace,
        repo_url,
        ref,
        build_image,
        docker_host,
        image_name,
        git_credentials=None,
        push_secret=None,
        memory_limit=0,
        memory_request=0,
        node_selector=None,
        appendix="",
        log_tail_lines=100,
        sticky_builds=False,
    ):
        """
        Parameters
        ----------

        q : tornado.queues.Queue
            Queue that receives progress events after the build has been submitted
        api : kubernetes.client.CoreV1Api()
            Api object to make kubernetes requests via
        name : str
            A unique name for the thing (repo, ref) being built. Used to coalesce
            builds, make sure they are not being unnecessarily repeated
        namespace : str
            Kubernetes namespace to spawn build pods into
        repo_url : str
            URL of repository to build.
            Passed through to repo2docker.
        ref : str
            Ref of repository to build
            Passed through to repo2docker.
        build_image : str
            Docker image containing repo2docker that is used to spawn the build
            pods.
        docker_host : str
            The docker socket to use for building the image.
            Must be a unix domain socket on a filesystem path accessible on the
            node in which the build pod is running.
        image_name : str
            Full name of the image to build. Includes the tag.
            Passed through to repo2docker.
        git_credentials : str
            Git credentials to use to clone private repositories. Passed
            through to repo2docker via the GIT_CREDENTIAL_ENV environment
            variable. Can be anything that will be accepted by git as
            a valid output from a git-credential helper. See
            https://git-scm.com/docs/gitcredentials for more information.
        push_secret : str
            Kubernetes secret containing credentials to push docker image to registry.
        memory_limit
            Memory limit for the docker build process. Can be an integer in
            bytes, or a byte specification (like 6M).
            Passed through to repo2docker.
        memory_request
            Memory request of the build pod. The actual building happens in the
            docker daemon, but setting request in the build pod makes sure that
            memory is reserved for the docker build in the node by the kubernetes
            scheduler.
        node_selector : dict
            Node selector for the kubernetes build pod.
        appendix : str
            Appendix to be added at the end of the Dockerfile used by repo2docker.
            Passed through to repo2docker.
        log_tail_lines : int
            Number of log lines to fetch from a currently running build.
            If a build with the same name is already running when submitted,
            only the last `log_tail_lines` number of lines will be fetched and
            displayed to the end user. If not, all log lines will be streamed.
        sticky_builds : bool
            If true, builds for the same repo (but different refs) will try to
            schedule on the same node, to reuse cache layers in the docker daemon
            being used.
        """
        self.q = q
        self.api = api
        self.repo_url = repo_url
        self.ref = ref
        self.name = name
        self.namespace = namespace
        self.image_name = image_name
        self.push_secret = push_secret
        self.build_image = build_image
        self.main_loop = IOLoop.current()
        self.memory_limit = memory_limit
        self.memory_request = memory_request
        self.docker_host = docker_host
        self.node_selector = node_selector
        self.appendix = appendix
        self.log_tail_lines = log_tail_lines

        self.stop_event = threading.Event()
        self.git_credentials = git_credentials

        self.sticky_builds = sticky_builds

        self._component_label = "binderhub-build"

    def get_cmd(self):
        """Get the cmd to run to build the image"""
        cmd = [
            'jupyter-repo2docker',
            '--ref', self.ref,
            '--image', self.image_name,
            '--no-clean', '--no-run', '--json-logs',
            '--user-name', 'jovyan',
            '--user-id', '1000',
        ]
        if self.appendix:
            cmd.extend(['--appendix', self.appendix])

        if self.push_secret:
            cmd.append('--push')

        if self.memory_limit:
            cmd.append('--build-memory-limit')
            cmd.append(str(self.memory_limit))

        # repo_url comes at the end, since otherwise our arguments
        # might be mistook for commands to run.
        # see https://github.com/jupyter/repo2docker/pull/128
        cmd.append(self.repo_url)

        return cmd

    @classmethod
    def cleanup_builds(cls, kube, namespace, max_age):
        """Delete stopped build pods and build pods that have aged out"""
        builds = kube.list_namespaced_pod(
            namespace=namespace,
            label_selector='component=binderhub-build',
        ).items
        phases = defaultdict(int)
        app_log.debug("%i build pods", len(builds))
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        start_cutoff = now - datetime.timedelta(seconds=max_age)
        deleted = 0
        for build in builds:
            phase = build.status.phase
            phases[phase] += 1
            annotations = build.metadata.annotations or {}
            repo = annotations.get("binder-repo", "unknown")
            delete = False
            if build.status.phase in {'Failed', 'Succeeded', 'Evicted'}:
                # log Deleting Failed build build-image-...
                # print(build.metadata)
                app_log.info(
                    "Deleting %s build %s (repo=%s)",
                    build.status.phase,
                    build.metadata.name,
                    repo,
                )
                delete = True
            else:
                # check age
                started = build.status.start_time
                if max_age and started and started < start_cutoff:
                    app_log.info(
                        "Deleting long-running build %s (repo=%s)",
                        build.metadata.name,
                        repo,
                    )
                    delete = True

            if delete:
                deleted += 1
                try:
                    kube.delete_namespaced_pod(
                        name=build.metadata.name,
                        namespace=namespace,
                        body=client.V1DeleteOptions(grace_period_seconds=0))
                except client.rest.ApiException as e:
                    if e.status == 404:
                        # Is ok, someone else has already deleted it
                        pass
                    else:
                        raise

        if deleted:
            app_log.info("Deleted %i/%i build pods", deleted, len(builds))
        app_log.debug("Build phase summary: %s", json.dumps(phases, sort_keys=True, indent=1))

    def progress(self, kind: ProgressEvent.Kind, payload: str):
        """
        Put current progress info into the queue on the main thread
        """
        self.main_loop.add_callback(self.q.put, ProgressEvent(kind, payload))

    def get_affinity(self):
        """Determine the affinity term for the build pod.

        There are a two affinity strategies, which one is used depends on how
        the BinderHub is configured.

        In the default setup the affinity of each build pod is an "anti-affinity"
        which causes the pods to prefer to schedule on separate nodes.

        In a setup with docker-in-docker enabled pods for a particular
        repository prefer to schedule on the same node in order to reuse the
        docker layer cache of previous builds.
        """
        resp = self.api.list_namespaced_pod(
            self.namespace,
            label_selector="component=dind,app=binder",
            _request_timeout=KUBE_REQUEST_TIMEOUT,
            _preload_content=False,
        )
        dind_pods = json.loads(resp.read())

        if self.sticky_builds and dind_pods:
            node_names = [pod["spec"]["nodeName"] for pod in dind_pods["items"]]
            ranked_nodes = rendezvous_rank(node_names, self.repo_url)
            best_node_name = ranked_nodes[0]

            affinity = client.V1Affinity(
                node_affinity=client.V1NodeAffinity(
                    preferred_during_scheduling_ignored_during_execution=[
                        client.V1PreferredSchedulingTerm(
                            weight=100,
                            preference=client.V1NodeSelectorTerm(
                                match_expressions=[
                                    client.V1NodeSelectorRequirement(
                                        key="kubernetes.io/hostname",
                                        operator="In",
                                        values=[best_node_name],
                                    )
                                ]
                            ),
                        )
                    ]
                )
            )

        else:
            affinity = client.V1Affinity(
                pod_anti_affinity=client.V1PodAntiAffinity(
                    preferred_during_scheduling_ignored_during_execution=[
                        client.V1WeightedPodAffinityTerm(
                            weight=100,
                            pod_affinity_term=client.V1PodAffinityTerm(
                                topology_key="kubernetes.io/hostname",
                                label_selector=client.V1LabelSelector(
                                    match_labels=dict(
                                        component=self._component_label
                                    )
                                )
                            )
                        )
                    ]
                )
            )

        return affinity

    def submit(self):
        """
        Submit a build pod to create the image for the repository.

        Progress of the build can be monitored by listening for items in
        the Queue passed to the constructor as `q`.
        """
        volume_mounts = [
            client.V1VolumeMount(mount_path="/var/run/docker.sock", name="docker-socket")
        ]
        docker_socket_path = urlparse(self.docker_host).path
        volumes = [client.V1Volume(
            name="docker-socket",
            host_path=client.V1HostPathVolumeSource(path=docker_socket_path, type='Socket')
        )]

        if self.push_secret:
            volume_mounts.append(client.V1VolumeMount(mount_path="/root/.docker", name='docker-config'))
            volumes.append(client.V1Volume(
                name='docker-config',
                secret=client.V1SecretVolumeSource(secret_name=self.push_secret)
            ))

        env = []
        if self.git_credentials:
            env.append(client.V1EnvVar(name='GIT_CREDENTIAL_ENV', value=self.git_credentials))

        self.pod = client.V1Pod(
            metadata=client.V1ObjectMeta(
                name=self.name,
                labels={
                    "name": self.name,
                    "component": self._component_label,
                },
                annotations={
                    "binder-repo": self.repo_url,
                },
            ),
            spec=client.V1PodSpec(
                containers=[
                    client.V1Container(
                        image=self.build_image,
                        name="builder",
                        args=self.get_cmd(),
                        volume_mounts=volume_mounts,
                        resources=client.V1ResourceRequirements(
                            limits={'memory': self.memory_limit},
                            requests={'memory': self.memory_request},
                        ),
                        env=env
                    )
                ],
                tolerations=[
                    client.V1Toleration(
                        key='hub.jupyter.org/dedicated',
                        operator='Equal',
                        value='user',
                        effect='NoSchedule',
                    ),
                    # GKE currently does not permit creating taints on a node pool
                    # with a `/` in the key field
                    client.V1Toleration(
                        key='hub.jupyter.org_dedicated',
                        operator='Equal',
                        value='user',
                        effect='NoSchedule',
                    ),
                ],
                node_selector=self.node_selector,
                volumes=volumes,
                restart_policy="Never",
                affinity=self.get_affinity()
            )
        )

        try:
            ret = self.api.create_namespaced_pod(
                self.namespace,
                self.pod,
                _request_timeout=KUBE_REQUEST_TIMEOUT,
            )
        except client.rest.ApiException as e:
            if e.status == 409:
                # Someone else created it!
                app_log.info("Build %s already running", self.name)
                pass
            else:
                raise
        else:
            app_log.info("Started build %s", self.name)

        app_log.info("Watching build pod %s", self.name)
        while not self.stop_event.is_set():
            w = watch.Watch()
            try:
                for f in w.stream(
                    self.api.list_namespaced_pod,
                    self.namespace,
                    label_selector="name={}".format(self.name),
                    timeout_seconds=30,
                    _request_timeout=KUBE_REQUEST_TIMEOUT,
                ):
                    if f['type'] == 'DELETED':
                        # Assume this is a successful completion
                        self.progress(ProgressEvent.Kind.BUILD_STATUS_CHANGE, ProgressEvent.BuildStatus.COMPLETED)
                        return
                    self.pod = f['object']
                    if not self.stop_event.is_set():
                        # Account for all the phases kubernetes pods can be in
                        # Pending, Running, Succeeded, Failed, Unknown
                        # https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-phase
                        phase = self.pod.status.phase
                        if phase == 'Pending':
                            self.progress(ProgressEvent.Kind.BUILD_STATUS_CHANGE, ProgressEvent.BuildStatus.PENDING)
                        elif phase == 'Running':
                            self.progress(ProgressEvent.Kind.BUILD_STATUS_CHANGE, ProgressEvent.BuildStatus.RUNNING)
                        elif phase == 'Succeeded':
                            # Do nothing! We will clean this up, and send a 'Completed' progress event
                            # when the pod has been deleted
                            pass
                        elif phase == 'Failed':
                            self.progress(ProgressEvent.Kind.BUILD_STATUS_CHANGE, ProgressEvent.BuildStatus.FAILED)
                        elif phase == 'Unknown':
                            self.progress(ProgressEvent.Kind.BUILD_STATUS_CHANGE, ProgressEvent.BuildStatus.UNKNOWN)
                        else:
                            # This shouldn't happen, unless k8s introduces new Phase types
                            warnings.warn(f"Found unknown phase {phase} when building {self.name}")

                    if self.pod.status.phase == 'Succeeded':
                        self.cleanup()
                    elif self.pod.status.phase == 'Failed':
                        self.cleanup()
            except Exception as e:
                app_log.exception("Error in watch stream for %s", self.name)
                raise
            finally:
                w.stop()
            if self.stop_event.is_set():
                app_log.info("Stopping watch of %s", self.name)
                return

    def stream_logs(self):
        """
        Stream build logs to the queue in self.q
        """
        app_log.info("Watching logs of %s", self.name)
        for line in self.api.read_namespaced_pod_log(
            self.name,
            self.namespace,
            follow=True,
            tail_lines=self.log_tail_lines,
            _request_timeout=(3, None),
            _preload_content=False,
        ):
            if self.stop_event.is_set():
                app_log.info("Stopping logs of %s", self.name)
                return
            # verify that the line is JSON
            line = line.decode('utf-8')
            try:
                json.loads(line)
            except ValueError:
                # log event wasn't JSON.
                # use the line itself as the message with unknown phase.
                # We don't know what the right phase is, use 'unknown'.
                # If it was a fatal error, presumably a 'failure'
                # message will arrive shortly.
                app_log.error("log event not json: %r", line)
                line = json.dumps({
                    'phase': 'unknown',
                    'message': line,
                })

            self.progress(ProgressEvent.Kind.LOG_MESSAGE, line)
        else:
            app_log.info("Finished streaming logs of %s", self.name)

    def cleanup(self):
        """
        Delete the kubernetes build pod
        """
        try:
            self.api.delete_namespaced_pod(
                name=self.name,
                namespace=self.namespace,
                body=client.V1DeleteOptions(grace_period_seconds=0),
                _request_timeout=KUBE_REQUEST_TIMEOUT,
            )
        except client.rest.ApiException as e:
            if e.status == 404:
                # Is ok, someone else has already deleted it
                pass
            else:
                raise

    def stop(self):
        """
        Stop wathcing for progress of build.
        """
        self.stop_event.set()

class FakeBuild(Build):
    """
    Fake Building process to be able to work on the UI without a running Minikube.
    """
    def submit(self):
        self.progress(ProgressEvent.Kind.BUILD_STATUS_CHANGE, 'Running')
        return

    def stream_logs(self):
        import time
        time.sleep(3)
        for phase in ('Pending', 'Running', 'Succeed', 'Building'):
            if self.stop_event.is_set():
                app_log.warning("Stopping logs of %s", self.name)
                return
            self.progress(ProgressEvent.Kind.LOG_MESSAGE,
                json.dumps({
                    'phase': phase,
                    'message': f"{phase}...\n",
                })
            )
        for i in range(5):
            if self.stop_event.is_set():
                app_log.warning("Stopping logs of %s", self.name)
                return
            time.sleep(1)
            self.progress('log',
                json.dumps({
                    'phase': 'unknown',
                    'message': f"Step {i+1}/10\n",
                })
            )
        self.progress(ProgressEvent.Kind.BUILD_STATUS_CHANGE, 'Succeeded')
        self.progress('log', json.dumps({
                'phase': 'Deleted',
                'message': f"Deleted...\n",
             })
        )
