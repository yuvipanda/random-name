import { NativeEventSource, EventSourcePolyfill } from 'event-source-polyfill';

const EventSource = NativeEventSource || EventSourcePolyfill;
var BASE_URL = $("#base-url").data().url;
var BUILD_TOKEN = $("#build-token").data().token;

export default function BinderImage(providerSpec) {
  this.providerSpec = providerSpec;
  this.callbacks = {};
  this.state = null;
}

BinderImage.prototype.fetch = function() {
  var apiUrl = BASE_URL + "build/" + this.providerSpec;
  if (BUILD_TOKEN) {
      apiUrl = apiUrl + `?build_token=${BUILD_TOKEN}`;
  }

  this.eventSource = new EventSource(apiUrl);
  var that = this;
  this.eventSource.onerror = function(err) {
    console.error("Failed to construct event stream", err);
    that.changeState("failed", {
      message: "Failed to connect to event stream\n"
    });
  };
  this.eventSource.addEventListener("message", function(event) {
    var data = JSON.parse(event.data);
    // FIXME: Rename 'phase' to 'state' upstream
    // FIXME: fix case of phase/state upstream
    var state = null;
    if (data.phase) {
      state = data.phase.toLowerCase();
    }
    that.changeState(state, data);
  });
};

BinderImage.prototype.close = function() {
  if (this.eventSource !== undefined) {
    this.eventSource.close();
  }
};

BinderImage.prototype.launch = function(url, token, path, pathType) {
  // redirect a user to a running server with a token
  if (path) {
    // strip trailing /
    url = url.replace(/\/$/, "");
    // trim leading '/'
    path = path.replace(/(^\/)/g, "");
    if (pathType === "file") {
      // trim trailing / on file paths
      path = path.replace(/(\/$)/g, "");
      // /tree is safe because it allows redirect to files
      // need more logic here if we support things other than notebooks
      url = url + "/tree/" + encodeURI(path);
    } else {
      // pathType === 'url'
      url = url + "/" + path;
    }
  }
  var sep = url.indexOf("?") == -1 ? "?" : "&";
  url = url + sep + $.param({ token: token });
  window.location.href = url;
};

BinderImage.prototype.onStateChange = function(state, cb) {
  if (this.callbacks[state] === undefined) {
    this.callbacks[state] = [cb];
  } else {
    this.callbacks[state].push(cb);
  }
};

BinderImage.prototype.validateStateTransition = function(oldState, newState) {
  if (oldState === "start") {
    return (
      newState === "waiting" || newState === "built" || newState === "failed"
    );
  } else if (oldState === "waiting") {
    return newState === "building" || newState === "failed";
  } else if (oldState === "building") {
    return newState === "pushing" || newState === "failed";
  } else if (oldState === "pushing") {
    return newState === "built" || newState === "failed";
  } else {
    return false;
  }
};

BinderImage.prototype.changeState = function(state, data) {
  var that = this;
  [state, "*"].map(function(key) {
    var callbacks = that.callbacks[key];
    if (callbacks) {
      for (var i = 0; i < callbacks.length; i++) {
        callbacks[i](that.state, state || that.state, data);
      }
    }
  });

  if (state && this.validateStateTransition(this.state, state)) {
    this.state = state;
  }
};
