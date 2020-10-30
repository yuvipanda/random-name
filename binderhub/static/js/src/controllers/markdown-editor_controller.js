import { Controller } from "stimulus"
import marked from 'marked/lib/marked.js'

export default class extends Controller {
  static targets = [ "url", "viewer" ]

  launch() {
    const element = this.urlTarget
    const url = element.value
    console.log("Hello! Launching:", url)
  }

  convertToMarkdown(event) {
    this.viewerTarget.innerHTML = marked(event.target.value, {sanitized: true});;
  }
}
