# Calibrating speaker-ID thresholds with few labels and certifying ~99% attribution precision

Context assumed throughout: 2 enrolled targets (Sri Preethaji, female; Sri Krishnaji, male), voiceprints from a handful of human-confirmed clips, per-video clustering, then cluster→identity matching by raw cosine (currently match ≥0.55, margin ≥0.15), abstain when unsure, ~650 videos, labelling budget of tens to low hundreds of clips.

Sample-size numbers marked "(computed)" were calculated for this note with `scipy.stats` (exact Clopper-Pearson via the Beta quantile, binomial and hypergeometric pmf/cdf). They are exact arithmetic on standard formulas, not taken from a paper.

## 1. Score normalisation (z/t/s/AS-norm): gains, cohort size, building a cohort from our own non-target clusters

### Takeaway
Adaptive s-norm (AS-norm) is the standard back-end for cosine-scored ECAPA-style embeddings. It gives roughly 10–30% relative gain in EER/minDCF. The gain is largest when some of the cohort matches the target domain, and it can be slightly negative when the cohort is too different from the evaluation data. Use the top 100–400 cohort scores out of a pool of about 1–3k one-per-speaker embeddings. Build that pool from our own non-target clusters, one embedding per distinct speaker, plus a generic pool, and reject outlier scores beyond ±4–5σ. AS-norm output is in z-units, so the current raw-cosine thresholds (0.55 / 0.15) do not carry over and have to be re-derived.

### Cited Findings
- **Formulas** (s(e,t) is the raw score; Sₑ are the cohort scores against the enrollment side, Sₜ against the test side):
  - Z-norm: (s − μ(Sₑ))/σ(Sₑ)
  - T-norm: (s − μ(Sₜ))/σ(Sₜ)
  - S-norm: ½[(s−μ(Sₑ))/σ(Sₑ) + (s−μ(Sₜ))/σ(Sₜ)]
  - Adaptive S-norm1: the same formula, but μ and σ come only from the top-X highest-scoring cohort members for each side (Eₑᵗᵒᵖ for enrollment, Eₜᵗᵒᵖ for test). X is typically 200.
  — [Matějka et al., Interspeech 2017](https://www.fit.vut.cz/research/groups/speech/publi/2017/matejka_interspeech2017_IS170803.pdf)
- **Gain, NIST SRE16 pooled trials** (DCFmin averaged over P_tar = 0.01 and 0.005): no norm 0.9538 → z-norm 0.7926 → t-norm 0.7514 → s-norm 0.7483 → AS-norm1 0.6797 with the matched SRE16-unlabeled cohort. That is about 30% relative. With a mismatched cohort (NIST only), AS-norm1 reached only 0.8922, a "slight improvement". ZT-norm was worst. — [Matějka 2017](https://www.fit.vut.cz/research/groups/speech/publi/2017/matejka_interspeech2017_IS170803.pdf)
- **Cohort size**: DCFmin vs top-X shows "nice flat minima between 200-500, we prefer 200". Using all cohort data (non-adaptive) was worse. When matched data are in the cohort, the adaptive version always beats the full-cohort version. — [Matějka 2017](https://www.fit.vut.cz/research/groups/speech/publi/2017/matejka_interspeech2017_IS170803.pdf)
- **Cohort composition**: best results came from a pool of several languages and channels with an in-domain subset (NIST+LID+SRE16unlab gave 0.6733). "If the cohort is too different, the performance can even degrade" (observed on SRE10). Adaptively selected cohorts matched the trial's language 68% of the time and its gender 92% of the time. — [Matějka 2017](https://www.fit.vut.cz/research/groups/speech/publi/2017/matejka_interspeech2017_IS170803.pdf)
- **Building a cohort from unlabelled data** (directly relevant to us): the cohort assumes one file per speaker. "When designing the cohort set on data without speaker labels, it is better to run unsupervised speaker clustering and take only one file from each cluster." Also reject cohort scores outside a "safe" interval of ±4–5 SD around the mean. — [Matějka 2017](https://www.fit.vut.cz/research/groups/speech/publi/2017/matejka_interspeech2017_IS170803.pdf)
- **ECAPA-TDNN**: cosine scoring plus AS-norm, with the impostor cohort built from speaker-wise averages of length-normalised training embeddings. Cohort size 1000 on in-domain VoxCeleb tests and "a more robust value of 50" for cross-dataset VoxSRC19. MinDCF used P_target = 10⁻², C_FA = C_Miss = 1. ECAPA (C=1024) scored EER 0.87% / MinDCF 0.1066 on Vox1-O. — [Desplanques et al., ECAPA-TDNN, arXiv 2005.07143](https://arxiv.org/pdf/2005.07143)
- **Recent measured AS-norm gain on ECAPA (2026)**: cosine → AS-norm (top 100 per side, cohort = VoxCeleb2-dev speaker centroids) took EER from 0.936/1.054/1.978% to 0.840/0.979/1.809% on Vox1-O/E/H, about 7–10% relative. Adding QMF calibration brought it to 0.766/0.932/1.693%. — [Li & Lee, "Unified Uncertainty-Aware Back-End", arXiv 2609.01221](https://arxiv.org/pdf/2609.01221)
- **WeSpeaker recipe guidance**: take 2000–3000 utterances from training data as the cohort and use AS-norm with top-n = 200–400. — [WeSpeaker VoxCeleb tutorial (via search snippet)](http://wenet.org.cn/wespeaker/vox.html)
- **IDLab VoxSRC-20** used AS-norm with an impostor cohort of 100 speaker-averaged embeddings. — [Thienpondt et al., arXiv 2010.11255](https://arxiv.org/pdf/2010.11255)

### Inferences
- **Cohort recipe for this corpus.** Run cross-video clustering on all non-target clusters (hosts, narrators, translators recur across videos) and keep one centroid per distinct speaker. Every cluster that is, or might be, a target must be excluded. A target-contaminated cohort inflates μ and suppresses true matches. Pool this with a generic set of about 1–2k speaker centroids, e.g. VoxCeleb2-dev, ideally with some Indian-English and Telugu/Tamil/Hindi speech. Use AS-norm with top-N ≈ 100–200. With only a few hundred in-domain non-target speakers, N = 50–100 matches ECAPA's cross-domain setting and is the safer choice.
- **Two targets, two genders.** Adaptive selection picks same-gender cohorts about 92% of the time, so AS-norm should automatically calibrate each voiceprint against same-gender hosts and translators. Male translators are exactly the confusers for Sri Krishnaji. Female hosts and translators are the confusers for Sri Preethaji.
- **The margin rule should be applied after normalisation.** The margin is s_norm(best target) − s_norm(other target). The between-target comparison should rarely be the binding constraint because the two targets differ in gender. The real risk is target vs a same-gender non-target, and AS-norm is designed to handle exactly that case.

### Gaps
- There is no published measurement of AS-norm on cluster-centroid-vs-voiceprint trials in lecture/satsang audio. The gain in our domain has to be measured on our own labelled set.
- The WeSpeaker recommendation came from a search snippet. The docs page itself was not fetched.

## 2. Enrollment amount, multi-session enrollment, test-duration effects, cluster-level vs segment-level

### Takeaway
Duration dominates. With ECAPA, EER is almost flat from full length (~8 s) down to 5 s, then degrades fast: about 1.7× at 2 s and about 3× at 1 s. Enrollment of ≤3 s is badly unstable, and 10 s is far better. Averaging embeddings over several enrollment clips from different videos is the standard, adequate approach, performing close to concatenation. So enroll with ≥30–60 s of clean speech per target spread over ≥3–5 videos, decide at the cluster level (centroid over many seconds), and never attribute on sub-2 s segments by themselves.

### Cited Findings
- **Test-duration curve, ECAPA-TDNN on VoxCeleb1-O without AS-norm** (full-length enrollment, test cropped): EER full 1.03%, 5 s 1.05%, 2 s 1.76%, 1.5 s 2.12%, 1 s 3.04%. The best 2025 short-segment system (S4) scored 0.78 / 0.81 / 1.24 / 1.46 / 2.29%. — [Myoung et al., arXiv 2509.19721](https://arxiv.org/pdf/2509.19721)
- The VoxCeleb1 test set averages about 8 s per utterance, and short-segment protocols truncate test utterances to 2/3/4 s. — [search summary of arXiv 2303.11020 / 2204.01005](https://arxiv.org/pdf/2303.11020)
- **Enrollment duration (2026, short test <3 s)**: text-independent enrollment of 3 s gave EER 8.86%. "As the TI duration increases from 1s to 10s, the EER continuously decreases", reaching about 1.98% at 10 s. TI enrollment beats text-dependent enrollment once T > 3 s. — [Ai et al., "Stabilizing Short Duration Speaker Verification…", arXiv 2606.16115](https://arxiv.org/html/2606.16115v1)
- **Multi-enrollment**: "a frequently made choice is to average speaker embedding[s]". On CNCeleb, which has multiple varied enrollment utterances, cosine scoring gave EER 11.86% with mean-embedding enrollment vs 12.46% with concatenation (ResNet). For TDNN it was 19.86% vs 20.82%. PLDA "multi-session" scoring was worse (21–22%). A trained attention back-end reached 10.77%. — [Zeng et al., "Attention back-end… multiple enrollment utterances", arXiv 2104.01541](https://arxiv.org/pdf/2104.01541)
- **NIST SRE24** uses nested 60/30/10 s enrollment segments (SAD speech), treating enrollment speech duration as a primary evaluation factor. — [NIST SRE24 Evaluation Plan](https://www.nist.gov/system/files/documents/2024/06/11/NIST_2024_Speaker_Recognition_Evaluation_Plan.pdf)
- **Matějka's SRE16 setup**: 60 s speech enrollment, tests 10–60 s. — [Matějka 2017](https://www.fit.vut.cz/research/groups/speech/publi/2017/matejka_interspeech2017_IS170803.pdf)
- **Duration as a calibration feature**: IDLab calibrates with l(s) = w_s·s + w_qᵀq + b, where q holds quality measures. Duration is the most effective single measure, used as symmetric min/max over both sides of the trial. Speech duration plus impostor-mean QMF improved EER by 11% and MinDCF by 3% on average over the fine-tuned baseline. Calibration trials were 10k each of short-short, short-long and long-long, where short means 2–6 s. — [Thienpondt et al., IDLab VoxSRC-20, arXiv 2010.11255](https://arxiv.org/pdf/2010.11255)

### Inferences
- **Enrollment recipe.** For each target, pick ≥5 clips from ≥3–5 different videos (different halls, microphones, years), each ≥6–10 s of single-speaker speech, for a total ≥60 s. Store per-clip embeddings as well as their L2-normalised mean. Averaging across sessions averages out channel, which is the multi-session benefit. The per-clip set also gives a "leave-one-clip-out" target-score distribution for free: score each held-out clip against the mean of the others. This is the cheapest estimate of P_miss.
- **Cluster-level decisions.** Score the cluster centroid, the mean of segment embeddings, or better, an embedding of up to about 30–60 s of the cluster's longest clean segments. The curve saturates beyond about 5–8 s, so clusters with ≥10 s of speech sit on the flat part. Any cluster with less than about 3–5 s total speech should abstain automatically, because EER roughly doubles or triples there.
- **Segment-level risk is at boundaries.** A cluster-level decision can still mislabel individual segments that clustering wrongly merged into the cluster, e.g. translator turns interleaved with the teacher's. Add a segment-level consistency check: each segment ≥2 s must individually score above a lower bar against the assigned target, or it is dropped from the attribution. Segments <2 s inherit the label only if both neighbours share it.

### Gaps
- There is no clean published curve for EER vs number of enrollment sessions (1 vs 3 vs 10) for modern ECAPA/ResNet embeddings. The SRE-era 1-vs-3-conversation results were not retrieved.
- No paper was found that directly compares cluster-level and segment-level attribution error in diarization-plus-identification pipelines.

## 3. Choosing an operating point for a target FAR (e.g., 0.1%) with few labels; minDCF with low P_target

### Takeaway
Precision depends on FAR and on the target prior, not on FAR alone. Precision = π(1−P_miss) / [π(1−P_miss) + (1−π)·FAR], where π is the fraction of candidate clusters that really are a target. In these videos targets are common (π ≈ 0.3–0.5), so 99% precision needs only FAR ≈ 0.3–0.9%. Certifying FAR ≤0.1% takes ~3,000 non-target trials with zero false accepts. That is unaffordable with human labels, but the non-target trials can come label-free from external impostor speech plus our own cross-video non-target clusters. The practical recipe is:
1. Set the threshold on AS-normed scores from a large non-target trial pool.
2. Calibrate to log-likelihood ratios (LLRs) with logistic regression plus duration.
3. Use the Bayes threshold log β.
4. Certify the end result with the precision audit in §4.

### Cited Findings
- **NIST cost model**: C_Det(θ) = C_Miss·P_Target·P_Miss(θ) + C_FA·(1−P_Target)·P_FA(θ). Normalised, C_Norm = P_Miss + β·P_FA with β = (C_FA/C_Miss)·(1−P_Target)/P_Target. "Actual detection costs will be computed … by applying detection thresholds of log(β)" to LLR scores. SRE24 uses C_Miss = C_FA = 1, P_Target = 0.01 and 0.005. minDCF uses the threshold that minimises cost. — [NIST SRE24 Evaluation Plan](https://www.nist.gov/system/files/documents/2024/06/11/NIST_2024_Speaker_Recognition_Evaluation_Plan.pdf)
- SRE16/18/19 used the same P_Target pair (0.01 / 0.005). VoxSRC uses P_target = 0.05. — [NIST SRE16 plan](https://www.nist.gov/system/files/documents/itl/iad/mig/SRE16_Eval_Plan_V1-0.pdf); [IDLab VoxSRC-20, arXiv 2010.11255](https://arxiv.org/pdf/2010.11255)
- **Calibration**: logistic regression maps scores to LLRs. A plain affine map is monotonic and cannot change EER/minDCF. Adding quality terms (duration, impostor mean) makes the threshold condition-dependent and does improve fixed-threshold metrics. — [Thienpondt et al., arXiv 2010.11255](https://arxiv.org/pdf/2010.11255)
- Normalisation improves score comparability but "does not guarantee well-calibrated likelihood ratios and may leave trial-dependent calibration errors". Duration, embedding magnitude and impostor statistics are the standard quality features. — [Li & Lee 2026, arXiv 2609.01221](https://arxiv.org/pdf/2609.01221)
- **Zero-failure bound**: 0 events in n gives a one-sided 95% upper bound of about 3/n (−ln 0.05 ≈ 2.996). Hanley & Lippman-Hand, JAMA 1983. — [Rule of three (statistics)](https://en.wikipedia.org/wiki/Rule_of_three_(statistics))
- **Non-target trials needed with zero false accepts** (computed, exact one-sided 95%):

  | FAR to certify | Non-target trials, 0 false accepts |
  |---|---|
  | ≤1% | 299 |
  | ≤0.1% | 2,995 |
  | ≤0.01% | ~29,956 |

- **Maximum FAR for a precision target**, from the precision formula above (computed):

  | Prior π | P_miss | Max FAR for 99% precision | Max FAR for 99.9% precision |
  |---|---|---|---|
  | 0.1 | 0.3 | 0.079% | 0.0078% |
  | 0.3 | 0.3 | 0.30% | 0.030% |
  | 0.5 | 0.1 | 0.91% | 0.090% |

  Abstention raises P_miss, which slightly tightens the required FAR.

### Inferences
- **Estimate π, don't assume it.** The prior is per candidate cluster, and it controls everything. For videos whose metadata says a teacher speaks, π per cluster is high. For compilations and host-led videos it is low. If the pipeline also runs on videos with no target at all, π drops and the FAR requirement tightens about 10×. Consider gating: attribute only in videos whose title/description/channel indicates a teacher, which raises π.
- **Label-free non-target pool.**
  1. Score each target voiceprint against every cross-video non-target centroid from §1. Tens to hundreds of distinct speakers across 650 videos yield hundreds to thousands of in-domain trials.
  2. Add thousands of external same-gender speakers (VoxCeleb centroids and similar).
  3. Pick the threshold as the (1 − FAR) quantile of AS-normed non-target scores. By construction AS-normed impostor scores are roughly zero-mean, unit-variance per trial, so FAR 10⁻³ lands around z ≈ 3.1 under normality. Treat that as a starting point only: impostor tails are usually heavier than Gaussian, so validate empirically.
  4. With ≥3,000 in-domain-ish non-target trials and 0 exceedances, FAR ≤0.1% is certified at 95%.
  5. External-corpus trials only bound FAR against those external speakers. The dangerous non-targets are the recurring translators and hosts, so in-domain clusters must dominate the pool.
- **Where to put the threshold under calibration.** Fit logistic-regression calibration with quality features (min/max speech duration of cluster and enrollment) on AS-normed scores. Use the few labelled target clusters plus the large non-target pool, and weight classes to the chosen prior. Then accept when LLR ≥ log β, where β = (1−π_eff)/π_eff and π_eff is deliberately set low (0.01 → θ = ln 99 ≈ 4.6; 0.001 → θ ≈ 6.9) to buy precision. Few target labels matter less here: C_FA dominates at low P_target, so the threshold is driven mostly by the non-target tail, which is cheap to sample.
- **Margin rule.** Keep a second-best-identity margin as a separate abstain condition. With only two genders-distinct targets it will seldom bind. It is still useful for cluster purity: a mixed cluster (teacher plus translator) tends to yield a lower top score and a smaller gap.

### Gaps
- There is no published FAR-at-10⁻³ calibration study specifically for few-shot enrollment of two known speakers in long-form lecture audio.
- Brümmer/Cumani calibration papers (e.g., Cllr, discriminative calibration) were not fetched. The log β threshold rule is cited from the NIST plan only.

## 4. Statistical certification of precision via sampling (Clopper-Pearson, Wilson, rule of three, stratified, LQAS)

### Takeaway
To claim precision ≥99% at 95% confidence you need a random sample of named attributions, checked by humans:
- 299 with 0 errors, or
- 473 with ≤1 error, or
- 628 with ≤2 errors.

For ≥99.5% the counts are 598, 947 and 1,258. A "low hundreds" budget can certify 99% only if the true error rate is well below 1%. At a true 0.3% error, a 0-error test on 299 passes only 41% of the time. Per-video certification of all 650 videos is statistically unaffordable. Certify the population, and use small per-video LQAS samples only to catch bad videos.

### Cited Findings
- **Rule of three**: 0 events in n gives [0, 3/n] as a 95% CI, one-sided, good for n > 30. Derived from (1−p)ⁿ = 0.05. Hanley & Lippman-Hand, JAMA 249(13):1743–5, 1983. — [Rule of three](https://en.wikipedia.org/wiki/Rule_of_three_(statistics))
- **Exact one-sided 95% Clopper-Pearson upper bound on error rate** (computed; upper = Beta⁻¹(0.95; k+1, n−k)):

  | n | 0 errors | 1 error |
  |---|---|---|
  | 50 | 5.8% | 9.1% |
  | 100 | 2.95% | 4.7% |
  | 150 | 1.98% | 3.1% |
  | 200 | 1.49% | 2.35% |
  | 300 | 0.99% | 1.57% |
  | 500 | 0.60% | 0.95% |

- **Sample size to certify error ≤ p at 95%, one-sided exact** (computed):

  | Error ≤ p | 0 errors | 1 error | 2 errors | 3 errors |
  |---|---|---|---|---|
  | 1% | 299 | 473 | 628 | 773 |
  | 0.5% | 598 | 947 | 1,258 | 1,549 |
  | 0.1% | 2,995 | 4,742 | 6,294 | 7,752 |

  At 99% confidence and p = 1%: 459 / 662 / 838 for 0 / 1 / 2 errors.
- **Wilson score (one-sided, z = 1.645)** is slightly less conservative: 0/299 gives an upper bound of 0.90% (vs CP 0.99%), and 0/100 gives 2.6%. For a certification claim, exact CP is the defensible choice. (computed)
- **Operating characteristic (probability the audit passes)** (computed):

  | True error rate | 0 errors in 299 | ≤1 in 473 | ≤2 in 628 |
  |---|---|---|---|
  | 0.1% | 74% | 92% | 97% |
  | 0.3% | 41% | 59% | 71% |
  | 0.5% | 22% | 32% | 39% |
  | 1.0% | 5% | 5% | 5% |
  | 2.0% | ≤0.2% | ≤0.2% | ≤0.2% |

  At 1.0% every design passes 5% of the time by construction.
- **LQAS basics**: classify each lot (here, a video) as acceptable or not from a small sample with a decision rule d*, choosing n and d* so that α and β (misclassification risks) stay below the target. The classic public-health design uses n = 19 with thresholds 30 points apart for α, β ≤ 10%. — [LQAS review, PMC6824847](https://pmc.ncbi.nlm.nih.gov/articles/PMC6824847/); [PMC9104662](https://pmc.ncbi.nlm.nih.gov/articles/PMC9104662/)
- **Per-video acceptance, finite lot, accept only if 0 defects** (hypergeometric; computed): the table gives the probability of wrongly accepting a video that has D wrong attributions.

  | Named segments N | Sample n | D=1 | D=2 | D=4 | D=8 |
  |---|---|---|---|---|---|
  | 40 | 10 | 0.75 | 0.56 | 0.30 | 0.08 |
  | 40 | 20 | 0.50 | 0.24 | 0.05 | — |
  | 100 | 30 | 0.70 | 0.49 | 0.23 | 0.05 |

  Per-video LQAS catches grossly broken videos, e.g. a whole translator cluster mislabelled. It cannot certify 99% within one video.

### Inferences
- **Choose the unit.** Certify precision over what users see: named attributions, weighted by speech seconds or by quoted passages. Sample the unit you claim. If answers cite segments, sample segments (with a duration floor) rather than clusters.
- **Two-stage plan within about 300–500 labels:**
  1. **Stratified random audit for certification.** Define strata by risk:
     - (a) low normalized-margin/LLR band just above threshold
     - (b) short clusters or segments (<5 s)
     - (c) segments adjacent to a speaker change (boundary ±2 s)
     - (d) videos with translators
     - (e) everything else

     Sample randomly within each stratum and oversample the high-risk ones. For the population claim, weight stratum error estimates by stratum share of attributions. A conservative bound is Σ_h W_h·UCB_h, with each UCB_h at 1−α/H (Bonferroni). Alternatively, certify the whole population with a single simple random sample of 299 or 473 and use the stratum oversample only for diagnosis.
  2. **Per-video LQAS as a screen.** For each new batch of videos, check 5–10 random attributions per video. Any error triggers a full review of that video and a look at why its clusters failed.
- **Make certification affordable by raising the bar.** The audit only passes reliably if the true error rate is about 0.1–0.3%. The cheapest lever is abstention: raise the LLR threshold or margin until the high-risk strata show ~0 errors in pilot labels, then run the certification sample. Every abstained cluster is excluded from the precision denominator, so precision rises at the cost of coverage.
- **Label quality matters.** A reviewer error rate of even 0.5% is comparable to the tolerance being certified. For any audited attribution judged "wrong", or unclear because of short or overlapped speech, require a second reviewer. Instruct reviewers to judge the specific time span, not the whole video.
- **Sequential option.** Using a sequential plan (e.g., stop at 299 if 0 errors, extend to 473 if 1 error, stop and fix if ≥2) keeps expected cost near 300 when the system is good. Report the exact CP bound for the final (k, n) and state that the plan was pre-specified.
- **Certify per target.** Each claim ("Sri Krishnaji said X", "Sri Preethaji said Y") matters separately, so certify each target separately. That doubles the sample (about 2×299), unless one pooled claim is acceptable.

### Gaps
- ANSI/ASQ Z1.4 tables were not retrieved. The LQAS figures are exact hypergeometric calculations, not Z1.4 code letters or AQL plans.
- The Clopper-Pearson/Wilson formulas are standard. They were applied computationally, but a primary textbook reference (Clopper & Pearson 1934, Biometrika) was not fetched.
- No source was found on combining stratified exact bounds optimally for rare-error certification. The Bonferroni-weighted sum above is a conservative construction, not a cited method.

## 5. Active-learning-style labelling: which clips to show humans first

### Takeaway
Labels have two different uses, and they must come from different samples:
- **Calibration and threshold-finding labels.** Actively chosen clips near the decision boundary are most informative here.
- **Certification labels.** These must be a probability sample, or the precision estimate is biased.

Spend the first ~50–100 labels on boundary/low-margin clusters to place the threshold and discover failure modes. Then spend a fresh random or stratified 300–500 on certification.

### Cited Findings
- AS-norm's adaptive cohort already surfaces the most confusable impostors: the top-scoring cohort members are, by construction, the non-targets closest to each voiceprint. — [Matějka 2017](https://www.fit.vut.cz/research/groups/speech/publi/2017/matejka_interspeech2017_IS170803.pdf)
- Quality-dependent errors concentrate in short-duration trials, which is why calibration sets are built with explicit short-short, short-long and long-long strata (2–6 s = short). — [Thienpondt et al., arXiv 2010.11255](https://arxiv.org/pdf/2010.11255)
- Short tests (<2 s) roughly double or triple EER relative to ≥5 s. — [Myoung et al., arXiv 2509.19721](https://arxiv.org/pdf/2509.19721)

### Inferences
Suggested label order:
1. **Enrollment verification** (~10–20 clips). Confirm each enrollment clip is pure single-speaker target speech. One contaminated enrollment clip (e.g., overlap with a translator) poisons the averaged voiceprint.
2. **Hard negatives** (~20–40). For each target, show the top-scoring non-target clusters: the adaptive-cohort "nearest impostors", typically same-gender translators and hosts. Confirming them as non-targets fixes the upper tail of the non-target distribution, which sets FAR. It also feeds the cohort and can become an explicit "known non-target" voiceprint list, which is a strong precision lever.
3. **Boundary band** (~20–40). Clusters whose calibrated LLR or normalized score falls within ±1 unit of the threshold, or whose top-2 margin is smallest. This is uncertainty sampling for placing the threshold.
4. **Structural risk** (~10–20). Short clusters (<5 s), clusters from videos with interpretation, and segments at speaker-change boundaries. These tell you whether to abstain on whole categories. Abstaining on a whole category is cheaper than certifying it.
5. **Then freeze the system and draw the certification sample** (§4). Any change to thresholds after seeing certification labels invalidates the certificate and requires a fresh sample.
- **Reusing actively chosen labels for estimation.** If actively chosen labels must also feed estimation, use importance weighting, where each label is weighted by 1/selection-probability, which requires recording the selection probabilities. Otherwise keep them strictly for calibration.

### Gaps
- No speaker-verification-specific study was found on active learning for threshold calibration under a small label budget. The ordering above is reasoned from the sources, not a measured result.
