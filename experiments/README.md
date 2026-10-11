# Experiment log

| id | parent | screen | dev acc | gain | P(better) | cost | outcome | hypothesis |
|---|---|---|---|---|---|---|---|---|
| **v000** | - | - | 0.775 | - | - | $0.47 | PROMOTED | baseline |
| **v001** | v000 | - | 0.85 | 3 | 0.919 | $0.45 | PROMOTED | The training batch had only one wrong case (mqx-071), so this is a single example, not a measured pattern. The failure has a reasoning cause that will likely re |
| gen1-cand1 | v000 | 6/10 vs 7 | 0.775 | 0 | 0.5 | - | rejected: not clearly better: +0 correct (need +1), P(better)=0.50 (ne | The one train failure (mqx-071) came from a reasoning mistake that could recur, not from missing knowledge. The neuro exam came back with an abnormal objective  |
| gen1-cand2 | v000 | 5/10 vs 7 | - | - | - | - | rejected: screened out: 5/10 vs parent 7/10 | The training batch had one failure (mqx-071), out of 20 cases. That's too little evidence to prove a pattern, but it shows a general weakness. The doctor truste |
| gen1-cand4 | v000 | 8/10 vs 7 | 0.825 | 2 | 0.832 | - | rejected: another candidate scored higher | The only training failure was a single case, so the evidence for this is thin. In that case (mqx-071) the doctor found the deciding sign itself: bilateral decre |

Diffs and proposals for every candidate are in `experiments/gen1/<candidate>/`; eval summaries in `experiments/evals/`.
