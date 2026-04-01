export const announcements = [
  'Hari Raya promotion briefing updated for this week.',
  'Remember to check SOP changes before opening shift.',
  'New honey sampler script added to Sales Guidelines.',
];

export const articles = [
  {
    id: 1,
    title: 'Wild Honey Product Information',
    category: 'Product',
    summary: 'Key benefits, flavour profile, and usage explanation for staff.',
    body: 'Wild Honey is one of the core Jungle House products. Staff should explain its flavour, source, key benefits, and suitable customer recommendations clearly and consistently.',
  },
  {
    id: 2,
    title: 'Opening SOP',
    category: 'SOP',
    summary: 'Opening checklist for kiosk setup, stock check, and cleanliness.',
    body: 'The opening SOP includes checking display stock, cleaning surfaces, testing POS readiness, preparing tasting samples, and confirming promotion notices before the kiosk starts operating.',
  },
  {
    id: 3,
    title: 'Closing SOP',
    category: 'SOP',
    summary: 'Closing checklist, cash handling, and storage reminders.',
    body: 'The closing SOP includes cleaning the kiosk, counting cash, recording sales summaries, securing stock, and preparing the kiosk for the next day.',
  },
  {
    id: 4,
    title: 'Customer Approach Sales Tips',
    category: 'Sales',
    summary: 'Basic script and approach for product recommendation.',
    body: 'Approach customers politely, identify interest, highlight product value, answer questions clearly, and invite tasting where suitable.',
  },
  {
    id: 5,
    title: 'New Staff Training Materials',
    category: 'Training',
    summary: 'Starter learning material for new staff onboarding.',
    body: 'Training materials cover product knowledge, SOP, customer communication, and common question handling for new staff onboarding.',
  },
];

export const notifications = [
  { id: 1, title: 'Escalation Alert', detail: 'A new unanswered question is waiting for follow-up.', read: false },
  { id: 2, title: 'Review Request', detail: 'A manual answer was submitted and needs manager review.', read: false },
  { id: 3, title: 'System Reminder', detail: 'Please review the updated promotion notice.', read: true },
];

export const escalations = [
  {
    id: 101,
    question: 'How should I explain honey gift set options during peak hour?',
    askedBy: 'Aina Staff',
    status: 'Pending',
    submittedAnswer: '',
  },
  {
    id: 102,
    question: 'What is the SOP if the tasting station runs out during rush hour?',
    askedBy: 'Farid Staff',
    status: 'Reviewing',
    submittedAnswer: 'Refill if stock is available and keep the station clean. Inform the team lead if supply is low.',
  },
  {
    id: 103,
    question: 'How to compare raw honey and infused honey for customers?',
    askedBy: 'Lina Staff',
    status: 'Resolved',
    submittedAnswer: 'Explain product difference based on ingredients, purpose, and taste profile.',
  },
];

export const quizItems = [
  { id: 1, title: 'Product Knowledge Quiz', questions: 10, lastScore: 80 },
  { id: 2, title: 'Opening SOP Quiz', questions: 8, lastScore: 90 },
  { id: 3, title: 'Sales Communication Quiz', questions: 12, lastScore: 75 },
];

export const dashboardStats = [
  { label: 'Knowledge Articles', value: 42 },
  { label: 'Questions This Week', value: 19 },
  { label: 'Pending Escalations', value: 3 },
  { label: 'Unread Notifications', value: 2 },
];

export const analyticsData = {
  topQuestions: [
    'How to explain honey benefits?',
    'What is the opening SOP?',
    'How to recommend gift sets?',
  ],
  knowledgeGaps: [
    'Promotion explanation during festive season',
    'Handling advanced customer health-related questions',
  ],
  searchTerms: ['closing sop', 'gift set', 'raw honey'],
};

export const mockUsers = [
  { id: 1, name: 'Aina Staff', email: 'aina@jh.test', role: 'staff', status: 'Active' },
  { id: 2, name: 'Brandon Lead', email: 'brandon@jh.test', role: 'teamlead', status: 'Active' },
  { id: 3, name: 'Cheryl Manager', email: 'cheryl@jh.test', role: 'manager', status: 'Active' },
  { id: 4, name: 'Farid Staff', email: 'farid@jh.test', role: 'staff', status: 'Inactive' },
];

export const reviewQueue = [
  {
    id: 1,
    question: 'What if customer asks whether honey is suitable for children?',
    answer: 'Staff should provide general product facts and avoid medical claims. Refer complex cases to the manager.',
    status: 'Pending',
  },
  {
    id: 2,
    question: 'How should staff explain the sampler set?',
    answer: 'Use a short comparison of flavour, purpose, and best-seller recommendations.',
    status: 'Approved',
  },
];
