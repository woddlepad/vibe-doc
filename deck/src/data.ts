// Real numbers from runs/ (v000 baseline, dev split, env 744e7905c8d1).
// Update this file when an improve run promotes a new version.

export type Outcome = 'correct' | 'hedged' | 'wrong'

export interface Visit {
  id: string
  gold: string
  said: string
  outcome: Outcome
  questions: number
  tests: number
}

const raw: [string, string, string, Outcome, number, number][] = [
  ['mqx-005', 'Pes anserine bursitis', 'Pes anserine bursitis / tendinopathy', 'hedged', 3, 5],
  ['mqx-008', 'Phyllodes tumor', 'Phyllodes tumor of the left breast', 'correct', 4, 5],
  ['mqx-011', 'Complex partial seizure', 'Focal impaired awareness seizures', 'correct', 4, 4],
  ['mqx-018', 'Uterine rupture', 'Complete uterine rupture', 'correct', 3, 4],
  ['mqx-019', 'Disc herniation', 'Acute L5-S1 disc herniation', 'correct', 3, 4],
  ['mqx-022', 'Malignant melanoma', 'Melanoma of the chest skin', 'correct', 2, 3],
  ['mqx-027', 'Adhesive capsulitis', 'Primary adhesive capsulitis', 'correct', 3, 3],
  ['mqx-028', 'Lung cancer', 'Acute symptomatic hyponatremia', 'wrong', 4, 8],
  ['mqx-031', 'Chronic lymphocytic leukemia', 'CLL / small lymphocytic lymphoma', 'hedged', 3, 5],
  ['mqx-034', 'Erythema infectiosum', 'Erythema infectiosum', 'correct', 4, 2],
  ['mqx-037', 'Multiple system atrophy', 'Multiple system atrophy', 'correct', 4, 3],
  ['mqx-038', 'Duodenal atresia', 'Congenital duodenal atresia', 'correct', 3, 4],
  ['mqx-045', 'Roseola infantum', 'Exanthem subitum', 'correct', 2, 3],
  ['mqx-046', 'Eczematous dermatitis', 'Chronic eczematous dermatitis', 'correct', 5, 4],
  ['mqx-047', 'Osteoarthritis', 'Osteoarthritis', 'correct', 3, 3],
  ['mqx-049', 'Stevens-Johnson syndrome', 'Stevens-Johnson syndrome', 'correct', 7, 6],
  ['mqx-061', 'Double aortic arch', 'Vascular ring, likely double arch', 'hedged', 3, 4],
  ['mqx-062', 'Molluscum contagiosum', 'Molluscum contagiosum', 'correct', 2, 1],
  ['mqx-066', 'Impaired erythropoietin production', 'Anemia of prematurity', 'correct', 6, 8],
  ['mqx-082', 'Breast milk jaundice', 'Breast milk jaundice', 'correct', 4, 6],
  ['mqx-087', 'Chronic lymphocytic leukemia', 'CLL / small lymphocytic lymphoma', 'hedged', 3, 6],
  ['mqx-104', 'Bronchiectasis', 'Chronic bacterial bronchitis', 'wrong', 8, 8],
  ['mqx-105', 'Erythema toxicum', 'Erythema toxicum neonatorum', 'correct', 3, 4],
  ['mqx-106', 'Myasthenia gravis', 'Generalized myasthenia gravis', 'correct', 5, 4],
  ['mqx-113', 'Bacillus cereus infection', 'Preformed-toxin food poisoning', 'correct', 4, 4],
  ['mqx-117', 'Schizophrenia', 'Schizophrenia', 'correct', 7, 5],
  ['mqx-128', 'Chickenpox', 'Varicella', 'correct', 4, 4],
  ['mqx-135', 'Hair tourniquet syndrome', 'Hair tourniquet syndrome', 'correct', 2, 3],
  ['mqx-140', "Bartter's syndrome", 'Bartter syndrome', 'correct', 2, 4],
  ['mqx-162', 'Dermatofibroma', 'Dermatofibroma', 'correct', 3, 4],
  ['mqx-163', 'Factitious disorder', 'Depressive disorder', 'wrong', 8, 10],
  ['mqx-179', 'Neuroleptic malignant syndrome', 'Neuroleptic malignant syndrome', 'correct', 4, 5],
  ['mqx-180', 'Atrial myxoma', 'Left atrial myxoma', 'correct', 5, 5],
  ['mqx-183', 'Ruptured ovarian cyst', 'Ruptured hemorrhagic ovarian cyst', 'correct', 3, 6],
  ['mqx-184', 'Lichen sclerosus', 'Vulvar lichen sclerosus', 'correct', 4, 2],
  ['mqx-187', 'Takotsubo cardiomyopathy', 'Acute coronary syndrome', 'wrong', 3, 7],
  ['mqx-197', 'Polycystic kidney disease', 'Polycystic kidney disease', 'correct', 5, 4],
  ['mqx-204', 'Gastric peptic ulcer', 'NSAID-associated gastric ulcer', 'correct', 5, 5],
  ['mqx-208', 'Central retinal artery occlusion', 'Central retinal artery occlusion', 'correct', 4, 3],
  ['mqx-212', "Crohn's disease", 'Ulcerative colitis', 'wrong', 6, 8],
]

export const visits: Visit[] = raw.map(([id, gold, said, outcome, questions, tests]) => ({
  id,
  gold,
  said,
  outcome,
  questions,
  tests,
}))

export const baseline = {
  version: 'v000',
  n: 40,
  correct: 31,
  accuracy: 0.775,
  ci95: [0.625, 0.877] as [number, number],
  meanQuestions: 4.0,
  meanTests: 4.65,
  budgetQuestions: 15,
  budgetTests: 10,
  secondsPerVisit: 37,
  dollarsPerVisit: 0.012,
  leaksBefore: 6,
  leaksAfter: 0,
}

export const split = { train: 115, dev: 40, test: 60 }

export const models = {
  doctor: 'Haiku 5.5',
  patient: 'Haiku 5.5',
  judge: 'Sonnet 5.5',
  optimizer: 'Opus 5.5',
}

export const gate = {
  candidates: 4,
  screen: 10,
  minConfidence: 0.75,
  minGain: 1,
}

// Generation 1 of `rsi improve` (runs/improve/20261011-223538), promoted as v001.
export const improved = {
  version: 'v001',
  correct: 34,
  accuracy: 0.85,
  ci95: [0.709, 0.929] as [number, number],
  confidence: 0.919,
  gain: 3,
  meanQuestions: 2.95,
  meanTests: 4.72,
  secondsPerVisit: 48,
  dollarsPerDevRun: 0.45,
  baselineDollarsPerDevRun: 0.47,
}

export type CandidateOutcome = 'promoted' | 'beaten' | 'no gain' | 'screened out'

export const candidates: { name: string; idea: string; correct: number | null; screen?: string; outcome: CandidateOutcome }[] = [
  { name: 'A', idea: 'Step-by-step workflow and a findings check', correct: 31, outcome: 'no gain' },
  { name: 'B', idea: 'Rules for weighing evidence', correct: null, screen: '5 of 10 on the quick screen', outcome: 'screened out' },
  { name: 'C', idea: 'Lessons first, a short check before submitting', correct: 33, outcome: 'beaten' },
  { name: 'D', idea: 'Findings are clues, a mandatory check, three lessons', correct: 34, outcome: 'promoted' },
]

// Dev cases whose outcome changed between v000 and v001.
export const flips = {
  fixed: [
    { gold: 'Bronchiectasis', before: 'Chronic bacterial bronchitis', after: 'Bronchiectasis, right middle lobe' },
    { gold: 'Chronic lymphocytic leukemia', before: 'CLL / SLL (hedged)', after: 'CLL' },
    { gold: 'Chronic lymphocytic leukemia', before: 'CLL / SLL (hedged)', after: 'CLL' },
    { gold: 'Double aortic arch', before: 'Vascular ring, likely double arch', after: 'Vascular ring, complete double arch' },
  ],
  broke: [{ gold: 'Breast milk jaundice', before: 'Breast milk jaundice', after: 'Crigler-Najjar syndrome type I' }],
}

// What the optimizer changed in the harness for v001.
export const harnessChanges = [
  { file: 'system.md', what: 'Two new sections: how findings work, and a mandatory check before submitting', status: 'edited' },
  { file: 'lessons.md', what: 'Three short lessons, written from the missed case', status: 'new' },
  { file: 'skills/', what: 'No skills added', status: 'unchanged' },
  { file: 'config.json', what: 'Tools and budgets as before: 15 questions, 10 tests', status: 'unchanged' },
  { file: 'Doctor model', what: 'Haiku 5.5, locked for every version', status: 'unchanged' },
] as const

export const addedCheck = [
  'List every abnormal finding from history, exam and tests.',
  'Your diagnosis must explain all of them. Never explain one away.',
  'When the patient’s report conflicts with an exam finding, trust the exam.',
  'Choose the most specific diagnosis. The distinguishing feature decides between close cousins.',
]
