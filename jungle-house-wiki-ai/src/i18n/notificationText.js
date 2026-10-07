// Notification text is stored in English by the backend; translate the known
// system messages at display time and leave anything else untouched.
const TITLE_KEYS = {
  'new notion page ready for review': 'notif.t.newNotion',
  'notion content changed': 'notif.t.notionChanged',
  'new account approval needed': 'notif.t.approvalNeeded',
  'account approved': 'notif.t.approved',
  'registration declined': 'notif.t.declined',
  'password changed': 'notif.t.pwChanged',
};

const DETAIL_PATTERNS = [
  { re: /^"(.*)" was found in Notion\. Review it in Notion Sync to add it to the Knowledge Base or discard it\.$/s, key: 'notif.d.newNotion', vars: (m) => ({ title: m[1] }) },
  { re: /^"(.*)" was edited in Notion\. Review it in Notion Sync to update or keep the current version\.$/s, key: 'notif.d.notionChanged', vars: (m) => ({ title: m[1] }) },
  { re: /^(.*) \((.*)\) has registered and is waiting for Manager \/ Team Leader approval\.$/s, key: 'notif.d.approvalNeeded', vars: (m) => ({ name: m[1], email: m[2] }) },
  { re: /^Your account was approved\. Sign in with your email and password\.$/, key: 'notif.d.approved', vars: () => ({}) },
  { re: /^Your registration was declined\. Contact your Manager for assistance\.(.*)$/s, key: 'notif.d.declined', vars: () => ({}), suffix: true },
  { re: /^Your Jungle House AI Wiki password was reset successfully\.$/, key: 'notif.d.pwChanged', vars: () => ({}) },
];


export function translateNotificationTitle(t, title) {
  const key = TITLE_KEYS[String(title || '').trim().toLowerCase()];
  return key ? t(key) : (title || t('notif.defaultTitle'));
}

export function translateNotificationDetail(t, detail) {
  const text = String(detail || '');
  for (const { re, key, vars, suffix } of DETAIL_PATTERNS) {
    const match = text.match(re);
    if (match) {
      const base = t(key, vars(match));
      return suffix && match[1] ? `${base}${match[1]}` : base;
    }
  }
  return text;
}
