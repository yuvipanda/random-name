import { Controller } from "stimulus"

export default class extends Controller {
  static targets = [ "editable" ]

  doubleClick(event) {
    event.preventDefault()

    let editor = document.createElement("input")
    editor.value = event.target.innerText

    let style = window.getComputedStyle(event.target)
    editor.style.cssText = style.cssText

    console.log(editor, event.pressure)
  }
}
