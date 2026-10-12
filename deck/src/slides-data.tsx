import { useState } from 'react'
import raw from './case-mqx-104.json'
import { split } from './data'
import { Slide } from './slides'
import type { Theme } from './themes'

/* ---------- 3: where the cases come from ---------- */

const sources = [
  {
    cite: 'Schmidgall, Ziaei, Harris, Kim, Reis, Jopling, Moor.',
    title: 'AgentClinic: a multimodal agent benchmark to evaluate AI in simulated clinical environments.',
    where: 'arXiv:2405.07960, 2024.',
  },
  {
    cite: 'Jin, Pan, Oufattole, Weng, Fang, Szolovits.',
    title: 'What disease does this patient have? A large-scale open domain question answering dataset from medical exams.',
    where: 'Applied Sciences 11(14):6421, 2021.',
  },
  {
    cite: 'github.com/SamuelSchmidgall/AgentClinic',
    title: 'agentclinic_medqa_extended.jsonl, used unchanged.',
    where: 'Commit b6fbe22, MIT license.',
  },
]

export function Dataset({ theme }: { theme: Theme }) {
  return (
    <Slide theme={theme} kind="dataset" n={3}>
      <h2>The cases come from AgentClinic.</h2>
      <div className="dataset">
        <figure className="ac-figure">
          <img src="/agentclinic-figure.webp" alt="AgentClinic diagram: a doctor agent, patient agent, measurement agent and moderator agent" />
          <figcaption>
            AgentClinic’s simulated clinic [1]. We keep its doctor, patient and measurement roles, put a frozen judge where the moderator
            sits, and leave out bias injection.
          </figcaption>
        </figure>
        <div className="ac-side">
          <dl className="ac-facts">
            <div>
              <dt>{split.train + split.dev + split.test}</dt>
              <dd>cases in AgentClinic-MedQA extended [3]</dd>
            </div>
            <div>
              <dt>USMLE</dt>
              <dd>board-exam questions from MedQA [2], rewritten as clinic visits</dd>
            </div>
            <div>
              <dt>
                {split.train} / {split.dev} / {split.test}
              </dt>
              <dd>our train, dev and test split</dd>
            </div>
          </dl>
          <ol className="sources">
            {sources.map((s) => (
              <li key={s.title}>
                {s.cite} <em>{s.title}</em> {s.where}
              </li>
            ))}
          </ol>
        </div>
      </div>
    </Slide>
  )
}

/* ---------- 4: one record, exactly as stored ---------- */

type Field = [key: string, value: string]

const blocks: { key: string; who: string; fields: Field[]; answer?: boolean }[] = [
  {
    key: 'Objective_for_Doctor',
    who: 'The doctor sees only this',
    fields: [['', 'Assess and diagnose the patient presenting with chronic cough and recurrent bouts of bronchitis.']],
  },
  {
    key: 'Patient_Actor',
    who: 'The patient sim',
    fields: [
      ['Demographics', '51-year-old woman'],
      ['History', 'An aggressive cough producing copious amounts of thick, foamy, yellow-green sputum for about 11 years… The patient is a non-smoker.'],
      ['Primary_Symptom', 'Aggressive cough with thick, yellow-green sputum'],
      ['Review_of_Systems', 'Denies any fever, weight loss, night sweats, or shortness of breath.'],
    ],
  },
  {
    key: 'Physical_Examination_Findings',
    who: 'The examiner',
    fields: [
      ['Vital_Signs', '36.7°C, 125/78 mmHg, 80 bpm, 16 breaths/min'],
      ['Auscultation', 'Crackles and wheezing over the right middle lobe.'],
      ['Percussion', 'Normal thoracic percussion note.'],
    ],
  },
  {
    key: 'Test_Results',
    who: 'The examiner',
    fields: [
      ['Chest_X-ray', 'Irregular opacities in the right middle lobe and diffuse airway thickening.'],
      ['Pulmonary_Function_Tests', 'FVC reduced, FEV1 reduced, FEV1/FVC normal'],
      ['Sputum_Culture', 'Heavy growth of non-specific bacteria, no TB or fungal growth.'],
    ],
  },
  {
    key: 'Correct_Diagnosis',
    who: 'Only the judge',
    fields: [['', 'Bronchiectasis']],
    answer: true,
  },
]

export function Record({ theme }: { theme: Theme }) {
  const [showRaw, setShowRaw] = useState(false)
  return (
    <Slide theme={theme} kind="record" n={4}>
      <div className="record-head">
        <h2>One case, as stored.</h2>
        <p className="visit-key">Case mqx-104, the patient you will meet again on slide 9. Each role sees only its own part.</p>
        <button className="thread-toggle raw-toggle" onClick={() => setShowRaw(!showRaw)} aria-pressed={showRaw}>
          {showRaw ? 'Show by role' : 'Show raw JSON'}
        </button>
      </div>
      {showRaw ? (
        <pre className="raw-json">{JSON.stringify(raw, null, 2)}</pre>
      ) : (
      <div className="osce">
        {blocks.map((b) => (
          <section key={b.key} className={`osce-block osce-${b.key} ${b.answer ? 'osce-answer' : ''}`}>
            <header>
              <code>{b.key}</code>
              <span className="osce-who">{b.who}</span>
            </header>
            {b.fields.map(([k, v]) => (
              <div key={k || v} className="osce-field">
                {k && <code>{k}</code>}
                <span>{v}</span>
              </div>
            ))}
          </section>
        ))}
      </div>
      )}
      <p className="foot">
        Anything not in the record comes back normal. The high-resolution CT the baseline ordered is not in this file. The chest X-ray is.
      </p>
    </Slide>
  )
}
