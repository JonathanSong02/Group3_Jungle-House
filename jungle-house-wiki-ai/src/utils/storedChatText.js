// Placeholder texts that AI Chat saves in English: in the browser's chat history and in what
// is sent to the server with an escalation. They stay stored in English so nothing that reads
// them changes; they are only shown in the selected language. Any other text is shown as-is.
const STORED_PLACEHOLDER_KEYS = {
  'New Chat': 'chat.newChat',
  'Uploaded an image': 'chat.uploadedImage',
  'Uploaded a file': 'chat.uploadedFile',
  'Selected option': 'chat.selectedOption',
};

export function displayStoredText(text, t) {
  const key = STORED_PLACEHOLDER_KEYS[text];
  return key ? t(key) : text;
}
