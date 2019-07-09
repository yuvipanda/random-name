export function autodetect(input) {
  // Based on https://github.com/Carreau/open-with-binder/blob/0bb0a5cb7c90865fd5736c19e4aea797ce6e25be/content_scripts/binderify.js
  var mybinderurl;
  try {
    var url = new URL(input.trim());
    var parts = url.pathname.split('/');

    if (url.hostname == 'github.com' && parts.length > 2) {
      mybinderurl = 'https://mybinder.org/v2/gh/' + parts[1] + '/' + parts[2] + '/' + (parts[4] || 'master');
      if (parts.length > 5) {
        mybinderurl += '?filepath=' + parts.slice(5).join('%2F');
      }
    }

    if (url.hostname == 'gist.github.com' && parts.length > 2) {
      mybinderurl = 'https://mybinder.org/v2/gist/' + parts[1] + '/' + parts[2] + '/' + (parts[3] || 'master');
    }

    if (url.hostname == 'gitlab.com' && parts.length > 2) {
      let repo = '';
      let extra = '';
      let branch_tag_hash = 'master';
      let blob_idx = parts.indexOf('blob');
      if (blob_idx === -1) {
        // tree is used instead of blob when looking at a directory so try
        // to find that instead
        blob_idx = parts.indexOf('tree');
      }
      if (blob_idx > 1){
        repo = parts.slice(1, blob_idx).join('/');
        branch_tag_hash = parts[blob_idx + 1];
        extra = '?filepath=' + parts.slice(blob_idx + 2).join('%2F')
      }
      else {
        repo = parts.slice(1).join('/');
      }
      mybinderurl = 'https://mybinder.org/v2/gl/' + encodeURIComponent(repo) + '/' + branch_tag_hash + extra;
    }
  } catch(err) {
    // Not a URL
    if (/^10\.\d{4,}[\.\d]*\/.+/.exec(input)) {
      mybinderurl = 'https://mybinder.org/v2/zenodo/' + input;
    }
  }
  return mybinderurl;
}
