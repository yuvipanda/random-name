/* If this file gets over 200 lines of code long (not counting docs / comments), start using a framework
  State transitions that are valid are:
  start -> waiting
  start -> built
  start -> failed
  waiting -> building
  waiting -> failed
  building -> pushing
  building -> failed
  pushing -> built
  pushing -> failed
*/
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import ClipboardJS from 'clipboard';
import 'xterm/css/xterm.css';
import 'bootstrap';

import BinderImage from './src/image';
import { markdownBadge, rstBadge } from './src/badge';
import { getPathType, updatePathText } from './src/path';
import { nextHelpText } from './src/loading';

import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap/dist/css/bootstrap-theme.min.css';
import '../index.css';

var BASE_URL = $('#base-url').data().url;
var BADGE_BASE_URL = $('#badge-base-url').data().url;
var config_dict = {};

function update_favicon(path) {
    var link = document.querySelector("link[rel*='icon']") || document.createElement('link');
    link.type = 'image/x-icon';
    link.rel = 'shortcut icon';
    link.href = path;
    document.getElementsByTagName('head')[0].appendChild(link);
}

function v2url(providerPrefix, repository, ref, path, pathType) {
  // return a v2 url from a providerPrefix, repository, ref, and (file|url)path
  if (repository.length === 0) {
    // no repo, no url
    return null;
  }
  if (BADGE_BASE_URL) {
    var url = BADGE_BASE_URL + 'v2/' + providerPrefix + '/' + repository + '/' + ref;
  }
  else {
    var url = window.location.origin + BASE_URL + 'v2/' + providerPrefix + '/' + repository + '/' + ref;
  }
  if (path && path.length > 0) {
    // encode the path, it will be decoded in loadingMain
    url = url + '?' + pathType + 'path=' + encodeURIComponent(path);
  }
  return url;
}

function loadConfig(callback) {
  var req = new XMLHttpRequest();
  req.onreadystatechange = function() {
    if (req.readyState == 4 && req.status == 200)
      callback(req.responseText)
  };
  req.open('GET', BASE_URL + "_config", true);
  req.send(null);
}

function setLabels() {
  var provider = $("#provider_prefix").val();
  var text = config_dict[provider]["text"];
  var tag_text = config_dict[provider]["tag_text"];
  var ref_prop_disabled = config_dict[provider]["ref_prop_disabled"];
  var label_prop_disabled = config_dict[provider]["label_prop_disabled"];
  var placeholder = "HEAD";

  $("#ref").attr('placeholder', placeholder).prop("disabled", ref_prop_disabled);
  $("label[for=ref]").text(tag_text).prop("disabled", label_prop_disabled);
  $("#repository").attr('placeholder', text);
  $("label[for=repository]").text(text);
}

function updateRepoText() {
  if (Object.keys(config_dict).length === 0){
    loadConfig(function(res) {
      config_dict = JSON.parse(res);
      setLabels();
    });
  } else {
    setLabels();
  }
}

function getBuildFormValues() {
  var providerPrefix = $('#provider_prefix').val().trim();
  var repo = $('#repository').val().trim();
  if (providerPrefix !== 'git') {
    repo = repo.replace(/^(https?:\/\/)?gist.github.com\//, '');
    repo = repo.replace(/^(https?:\/\/)?github.com\//, '');
    repo = repo.replace(/^(https?:\/\/)?gitlab.com\//, '');
  }
  // trim trailing or leading '/' on repo
  repo = repo.replace(/(^\/)|(\/?$)/g, '');
  // git providers encode the URL of the git repository as the repo
  // argument.
  if (repo.includes("://") || providerPrefix === 'gl') {
    repo = encodeURIComponent(repo);
  }

  var ref = $('#ref').val().trim() || $("#ref").attr("placeholder");
  if (providerPrefix === 'zenodo' || providerPrefix === 'figshare' || providerPrefix === 'dataverse' ||
      providerPrefix === 'hydroshare') {
    ref = "";
  }
  var path = $('#filepath').val().trim();
  return {'providerPrefix': providerPrefix, 'repo': repo,
          'ref': ref, 'path': path, 'pathType': getPathType()}
}

function updateUrls(formValues) {
  if (typeof formValues === "undefined") {
      formValues = getBuildFormValues();
  }
  var url = v2url(
               formValues.providerPrefix,
               formValues.repo,
               formValues.ref,
               formValues.path,
               formValues.pathType
            );

  if ((url||'').trim().length > 0){
    // update URLs and links (badges, etc.)
    $("#badge-link").attr('href', url);
    $('#basic-url-snippet').text(url);
    $('#markdown-badge-snippet').text(markdownBadge(url));
    $('#rst-badge-snippet').text(rstBadge(url));
  } else {
    ['#basic-url-snippet', '#markdown-badge-snippet', '#rst-badge-snippet' ].map(function(item, ind){
      var el = $(item);
      el.text(el.attr('data-default'));
    })
  }
}

function build(providerSpec, log, path, pathType) {
  update_favicon(BASE_URL + "favicon_building.ico");
  // split provider prefix off of providerSpec
  var spec = providerSpec.slice(providerSpec.indexOf('/') + 1);
  // Update the text of the loading page if it exists
  if ($('div#loader-text').length > 0) {
    $('div#loader-text p.launching').text("Starting repository: " + decodeURIComponent(spec))
  }

  $('#build-progress .progress-bar').addClass('hidden');
  log.clear();

  var image = new BinderImage(providerSpec);

  image.onStateChange('*', function(oldState, newState, data) {
    if (data.message !== undefined) {
      log.write(data.message);
      log.fit();
    } else {
      console.log(data);
    }
  });

  image.onStateChange('waiting', function(oldState, newState, data) {
    $('#phase-waiting').removeClass('hidden');
  });

  image.onStateChange('building', function(oldState, newState, data) {
    $('#phase-building').removeClass('hidden');
  });

  image.onStateChange('pushing', function(oldState, newState, data) {
    $('#phase-pushing').removeClass('hidden');
  });

  image.onStateChange('failed', function(oldState, newState, data) {
    $('#build-progress .progress-bar').addClass('hidden');
    $('#phase-failed').removeClass('hidden');

    $("#loader").addClass("paused");

    // If we fail for any reason, show an error message and logs
    update_favicon(BASE_URL + "favicon_fail.ico");
    if ($('div#loader-text').length > 0) {
      $('#loader').addClass("error");
      $('div#loader-text p.launching').html('Error loading ' + spec + '!<br /> See logs below for details.');
    }
    image.close();
  });

  image.onStateChange('built', function(oldState, newState, data) {
    if (oldState === null) {
      $('#phase-already-built').removeClass('hidden');
      $('#phase-launching').removeClass('hidden');
    }
    $('#phase-launching').removeClass('hidden');
    update_favicon(BASE_URL + "favicon_success.ico");
  });

  image.onStateChange('ready', function(oldState, newState, data) {
    image.close();
    // user server is ready, redirect to there
    image.launch(data.url, data.token, path, pathType);
  });

  image.fetch();
  return image;
}

function setUpLog() {
  const log = new Terminal({
    convertEol: true,
    disableStdin: true
  });
  const fitAddon = new FitAddon();
  log.loadAddon(fitAddon);

  log.fit = function () {
    fitAddon.fit();
  };

  log.open(parent=document.getElementById('log'), false);
  log.fit();

  $(window).resize(function() {
    log.fit();
  });

  return log;
}

function indexMain() {
    var log = setUpLog();

    // setup badge dropdown and default values.
    updateUrls();

    $("#provider_prefix_sel li").click(function(event){
      event.preventDefault();

      $("#provider_prefix-selected").text($(this).text());
      $("#provider_prefix").val($(this).attr("value"));
      updateRepoText();
      updateUrls();
    });

    $("#url-or-file-btn").find("a").click(function (evt) {
      evt.preventDefault();

      $("#url-or-file-selected").text($(this).text());
      updatePathText();
      updateUrls();
    });
    updatePathText();
    updateRepoText();

    $('#repository').on('keyup paste change', function(event) {updateUrls();});

    $('#ref').on('keyup paste change', function(event) {updateUrls();});

    $('#filepath').on('keyup paste change', function(event) {updateUrls();});

    $('#toggle-badge-snippet').on('click', function() {
        var badgeSnippets = $('#badge-snippets');
        if (badgeSnippets.hasClass('hidden')) {
            badgeSnippets.removeClass('hidden');
            $("#badge-snippet-caret").removeClass("glyphicon-triangle-right");
            $("#badge-snippet-caret").addClass("glyphicon-triangle-bottom");
        } else {
            badgeSnippets.addClass('hidden');
            $("#badge-snippet-caret").removeClass("glyphicon-triangle-bottom");
            $("#badge-snippet-caret").addClass("glyphicon-triangle-right");
        }

        return false;
    });

    $('#build-form').submit(function() {
        var formValues = getBuildFormValues();
        updateUrls(formValues);
        build(
          formValues.providerPrefix + '/' + formValues.repo + '/' + formValues.ref,
          log,
          formValues.path,
          formValues.pathType
        );
        return false;
    });
}

function loadingMain(providerSpec) {
  var log = setUpLog();
  // retrieve (encoded) filepath/urlpath from URL
  // URLSearchParams.get returns the decoded value,
  // that is good because it is the real value and '/'s will be trimmed in `launch`
  var params = new URL(location.href).searchParams;
  var pathType, path;
  path = params.get('urlpath');
  if (path) {
    pathType = 'url';
  } else {
    path = params.get('filepath');
    if (path) {
      pathType = 'file';
    }
  }
  build(providerSpec, log, path, pathType);

  // Looping through help text every few seconds
  const launchMessageInterval = 6 * 1000
  setInterval(nextHelpText, launchMessageInterval);

  // If we have a long launch, add a class so we display a long launch msg
  const launchTimeout = 120 * 1000
  setTimeout(() => {
    $('div#loader-links p.text-center').addClass("longLaunch");
    nextHelpText();
  }, launchTimeout)

  return false;
}

// export entrypoints
window.loadingMain = loadingMain;
window.indexMain = indexMain;

// Load the clipboard after the page loads so it can find the buttons it needs
window.onload = function() {
  new ClipboardJS('.clipboard');
};
