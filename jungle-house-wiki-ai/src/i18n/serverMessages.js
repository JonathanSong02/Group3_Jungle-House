// Backend responses are written in English. Translate the known ones at display
// time (exact matches and a few count-bearing patterns); anything else is shown as-is.
const EXACT = {
  "Notion sync service is not available on this server.": 'srv.e0',
  "Only managers can disconnect Notion.": 'srv.e1',
  "Only managers can check for Notion updates.": 'srv.e2',
  "Only managers can approve Notion updates.": 'srv.e3',
  "Only managers can dismiss Notion updates.": 'srv.e4',
  "Only managers can move Notion updates to Trash.": 'srv.e5',
  "Only managers can restore Notion updates.": 'srv.e6',
  "Only managers can permanently delete Notion updates.": 'srv.e7',
  "Only managers can restore Obsolete Notion articles.": 'srv.e8',
  "Notion disconnected.": 'srv.e9',
  "Failed to disconnect Notion.": 'srv.e10',
  "No Notion workspace is connected yet.": 'srv.e11',
  "No Notion workspace is connected. Reconnect Notion first.": 'srv.e12',
  "Your Notion connection needs to be renewed. Please reconnect Notion.": 'srv.e13',
  "Failed to start checking Notion for updates.": 'srv.e14',
  "Failed to load pending Notion updates.": 'srv.e15',
  "This update was already resolved.": 'srv.e16',
  "Failed to apply this update.": 'srv.e17',
  "Failed to dismiss this update.": 'srv.e18',
  "Moved to Trash.": 'srv.e19',
  "Failed to move this update to Trash.": 'srv.e20',
  "This item is not in Trash.": 'srv.e21',
  "Restored to Pending.": 'srv.e22',
  "Failed to restore this update.": 'srv.e23',
  "Item not found in Trash.": 'srv.e24',
  "Permanently deleted.": 'srv.e25',
  "Failed to permanently delete this update.": 'srv.e26',
  "No items selected.": 'srv.e27',
  "Failed to publish selected updates.": 'srv.e28',
  "Published to the Knowledge Base.": 'srv.e29',
  "Failed to move selected updates to Trash.": 'srv.e30',
  "Failed to restore selected updates.": 'srv.e31',
  "None of the selected items were found in Trash.": 'srv.e32',
  "Failed to permanently delete selected updates.": 'srv.e33',
  "Failed to load Obsolete Notion articles.": 'srv.e34',
  "Obsolete record not found.": 'srv.e35',
  "Failed to load this Obsolete article.": 'srv.e36',
  "Fetched the latest Notion version. Review it in Pending.": 'srv.e37',
  "This Notion page can no longer be accessed. It may have been deleted, archived, or removed from the integration's permissions.": 'srv.e38',
  "Failed to load Notion sync history.": 'srv.e39',
  "Notion connected successfully.": 'srv.e40',
  "Notion app credentials saved.": 'srv.e41',
  "Reverted to the server's default Notion app.": 'srv.e42',
  "Failed to save Notion app credentials.": 'srv.e43',
  "Failed to reset Notion app credentials.": 'srv.e44',
  "Storage cleanup completed.": 'srv.e45',
  "Failed to run the storage audit.": 'srv.e46',
  "Failed to run storage cleanup.": 'srv.e47',
  "Failed to start connecting to Notion.": 'srv.e48',
  "Failed to restore this article.": 'srv.e49',
  "Failed to check Notion for updates.": 'srv.e50',
  "Failed to load Notion connection status.": 'srv.e51',
  "Unable to publish selected items.": 'srv.e52',
  "Unable to move selected items to Trash.": 'srv.e53',
  "Unable to restore selected items.": 'srv.e54',
  "Unable to permanently delete selected items.": 'srv.e55',
  "Failed to resolve this update. It may have already been handled.": 'srv.e56',
  "Done.": 'srv.e57',
  "AI provider connected successfully.": 'srv.e58',
  "AI provider rejected the request: rate limit or quota exceeded (HTTP 429).": 'srv.e59',
  "AI provider connection failed. Please check your API key.": 'srv.e60',
};

const PATTERNS = [
  [/^(\d+) item\(s\) published to the Knowledge Base\.$/, 'srv.p0', (m) => ({ n: m[1] })],
  [/^(\d+) item\(s\) moved to Trash\.$/, 'srv.p1', (m) => ({ n: m[1] })],
  [/^(\d+) item\(s\) restored\.$/, 'srv.p2', (m) => ({ n: m[1] })],
  [/^(\d+) item\(s\) permanently deleted\.$/, 'srv.p3', (m) => ({ n: m[1] })],
  [/^(\d+) unused file\(s\) removed from storage\.$/, 'srv.p4', (m) => ({ n: m[1] })],
  [/^Checked Notion: (\d+) new, (\d+) updated, (\d+) unchanged\.(.*)$/, 'srv.p5', (m) => ({ a: m[1], b: m[2], c: m[3] })],
  [/^User status updated to (.*)\.$/, 'srv.p6', (m) => ({ a: m[1] })],
  [/^AI provider rejected the API key \(HTTP (\d+)\)\. Please check the key is correct and active\.$/, 'srv.p7', (m) => ({ a: m[1] })],
  [/^AI provider returned an error \(HTTP (\d+)\)\.$/, 'srv.p8', (m) => ({ a: m[1] })],
];

export function translateServerMessage(t, message) {
  if (!message || typeof message !== 'string') return message;
  const text = message.trim();
  if (EXACT[text]) return t(EXACT[text]);
  for (const [re, key, vars] of PATTERNS) {
    const match = text.match(re);
    if (match) {
      const tail = key === 'srv.p5' ? match[4] || '' : '';
      return t(key, vars(match)) + tail;
    }
  }
  return message;
}
