# 04-650 MF4ML project: TA check-in and viva questions

**For the teaching team only.** Use these at the mandatory check-ins, or in a short viva after
submission, to confirm that students understand their own derivations and code. Reference numbers
come from the reference-solution notebook (`mf4ml_reference_solution.ipynb`, seed 42, 80/20 splits,
z-scores fitted on training rows) unless stated otherwise.

## How to use this sheet

* **Ten minutes per student is enough.** Pick 3–4 questions for the part they are working on,
  including at least one ★ question and one *live probe*.
* **Ask them to drive.** Have the student open their notebook and point at the line that does
  each thing. "Where in your code…" questions show ownership better than "explain…" questions.
* **Ask for a prediction first.** In a live probe, ask "what will happen if…?" *before* they
  run the change. A student who wrote the code can usually predict the direction of the effect.
* **Different numbers are not wrong numbers.** Splits, seeds, λ, K and the positive class all
  change results. Rows marked *should match* are the exceptions.
* **Milestones.** The spec's work plan has check-ins on Nov 17 (Part A), Nov 20 (Part B),
  Nov 27 (Parts C–D) and Dec 2 (Parts E–F). The Part A and B questions also work at the later
  check-ins and in a final viva.

Each question lists: **Listen for** (what a good answer contains) and **Red flags**.

---

## Part A: Linear regression and matrix decompositions (diabetes)

**A1 ★ "Show me your design matrix. What shape is it, what is its rank, and how did you compute the rank?"**

* *Listen for:* 353 × 11 for an 80/20 split (10 features + an intercept column); rank 11, computed
  from the singular values with a tolerance (`np.linalg.matrix_rank` or σᵢ > tol·σ₁). The scaler is
  fitted on the training rows only.
* *Red flags:* cannot say which column is the intercept; scaler fitted before the split; "rank = 11
  because there are 11 columns".

**A2 "Why `np.linalg.solve` rather than `np.linalg.inv`? What does `solve` actually do?"**

* *Listen for:* it factorises (LU) and solves by substitution. That is cheaper and more accurate than
  forming the inverse and multiplying, and the spec forbids an explicit inverse.
* *Red flags:* `inv(X.T @ X) @ X.T @ y` anywhere in the notebook.

**A3 ★ "In your QR solution, why can you ignore part of the residual? Show me how you solve the triangular system."**

* *Listen for:* ‖Xβ − y‖² = ‖Rβ − Qᵀy‖² + ‖(I − QQᵀ)y‖², and the second term does not depend on β.
  Back substitution goes from the last row up: β_p = c_p / R_pp, then each βᵢ uses the β's already
  found.
* *Live probe:* "What happens if a diagonal entry of R is (nearly) zero?" → the corresponding column
  is (nearly) a linear combination of earlier columns, and you get division by ~0, i.e. rank
  deficiency.
* *Red flags:* uses `np.linalg.inv(R)`; cannot say why Q has orthonormal columns.

**A4 ★ "Prove κ₂(XᵀX) = κ₂(X)² on the board."**

* *Listen for:* thin SVD X = UΣVᵀ ⇒ XᵀX = VΣ²Vᵀ, so its singular values are σᵢ². The ratio σ₁²/σ_p²
  is the square of σ₁/σ_p. Full column rank is needed so that σ_p > 0.
* *Red flags:* argues with eigenvalues of X (undefined for a rectangular matrix); only treats square
  or symmetric X.

**A5 "How did you pick your gradient-descent learning rate? What happens at η = 2/λ_max(XᵀX/n)?"**

* *Listen for:* convergence needs 0 < η < 2/λ_max of H = XᵀX/n (≈ 0.50 for standardised diabetes);
  η = 1/λ_max is a safe choice. At exactly 2/λ_max the top eigen-direction flips sign every step
  without shrinking (|1 − ηλ| = 1). Iterations grow with κ(H) ≈ 430 (about 7,600 iterations to a
  10⁻⁸ gradient tolerance in the reference).
* *Live probe:* set η just above 2/λ_max and ask them to predict the loss curve (it diverges, with
  oscillating sign).

**A6 "Do your three solvers give the same test RMSE? Should they?"**

* *Should match:* yes, all three equal; **≈ 53.85** for a seed-42 80/20 split (roughly 50–58 for
  other splits). The value does not depend on whether they standardised, because with an intercept,
  per-feature affine rescaling does not change OLS predictions.
* *Red flags:* gradient descent visibly worse, and explained as "GD is less accurate" rather than
  "stopped early".

**A7 ★ "In your conditioning experiment, which effects come from the algorithm and which from the data?"**

* *Listen for:* *numerical* error (rounding): about u·κ(X) for QR and u·κ(X)² for the normal
  equations, best seen with noise-free y; *statistical* variability: Var(β̂) = σ²(XᵀX)⁻¹ blows up
  for either solver. Correlated coefficients are individually unstable, but their sum is stable.
  The SVD shows which direction is unidentifiable; truncated SVD or ridge fixes it.
* *Red flags:* only a noisy experiment, with all the instability blamed on the normal equations.

**A8 "When is XᵀX only positive semidefinite? Give an example you might meet in practice."**

* *Listen for:* vᵀXᵀXv = ‖Xv‖² ≥ 0 always; PD iff full column rank. Examples: p > n; a duplicated
  or derived feature; one-hot dummies for every level plus an intercept; a constant feature plus an
  intercept.

---

## Part B: Probability and logistic regression (breast cancer)

**B1 ★ "What does your model output for one patient, and what does the predicted label add?"**

* *Listen for:* an estimate of P(Y = 1 | x), a probability. The label is a *decision* made with a
  threshold that reflects costs. p = 0.9 still means a 1-in-10 chance of the other class.
* *Red flags:* treats the probability as a certainty or as "confidence that the label is right"
  without qualification.

**B2 ★ "Show me your sigmoid and your loss. What happens at z = −1000?" (live probe)**

* *Listen for:* separate branches for z ≥ 0 and z < 0, or an equivalent, so exp never overflows.
  The loss is computed from logits (`np.logaddexp(0, z) − y*z`), or with clipping that they can
  justify.
* *Red flags:* `RuntimeWarning: overflow` or `divide by zero in log`; `nan` loss for large step sizes.

**B3 "Derive the gradient of the average negative log-likelihood."**

* *Listen for:* σ′ = σ(1 − σ); the per-sample derivative simplifies to (pᵢ − yᵢ)x̃ᵢ, so the gradient
  is (1/n)X̃ᵀ(p − y). Bonus: the Hessian (1/n)X̃ᵀdiag(p(1−p))X̃ is PSD, so the loss is convex.

**B4 ★ "What maximum error did your finite-difference check report? What value would worry you?"**

* *Listen for:* about 10⁻¹⁰ to 10⁻⁷ with central differences and h ≈ 10⁻⁶. They can explain the
  trade-off in h (truncation error ∝ h² vs rounding error ∝ u/h). Anything around 10⁻³ or above
  means a bug (missing 1/n, sign error, penalised intercept left out of the numerical objective).
* *Red flags:* the check was done on the full dataset with a single coordinate, or compares the
  gradient with itself.

**B5 ★ "Did your unregularised model converge? Why or why not?"**

* *Listen for:* it did **not**, because the standardised training set is **linearly separable** (a
  perceptron reaches zero errors). The likelihood keeps improving as ‖w‖ → ∞, so there is no
  finite MLE. L2 regularisation gives a unique finite optimum.
* *Red flags:* "it just needs more iterations"; doesn't notice ‖w‖ growing.

**B6 "Your largest learning rate reached the lowest training loss. Is it the best model?"**

* *Listen for:* not necessarily. With no minimiser, a bigger step only moves faster towards
  ‖w‖ → ∞: over-confident probabilities and worse test log-loss. In the reference, η = 300 has
  training BCE 0.0007 but test log-loss 1.7, against about 0.11 for η = 0.3.

**B7 "Why don't you penalise the intercept? What is your λ in scikit-learn's terms?"**

* *Listen for:* the intercept sets the baseline log-odds (prevalence), and shrinking it biases every
  prediction towards 0.5. scikit-learn minimises C·Σloss + ½‖w‖², so λ = 1/(C·n). A mismatch with
  scikit-learn's *default* C = 1 is a penalty difference, not a bug.

**B8 "How did you choose λ and the threshold?"**

* *Listen for:* cross-validation or a validation split **inside the training set**. The reference
  gets λ = 10⁻³ from 5-fold CV log-loss. The threshold is set from costs or validation data, not by
  maximising test F1.
* *Red flags:* any hyperparameter picked by looking at test metrics.

**B9 "Which is your positive class? What happens to precision and recall if you flip it?"**

* *Listen for:* scikit-learn codes malignant = 0. Either choice is fine if stated, but precision and
  recall then refer to the other class. Reference (malignant = 1, τ = 0.5): accuracy 0.974,
  precision 0.976, recall 0.952, confusion matrix [[71, 1], [2, 40]].
* *Follow-up:* "Why is accuracy alone not enough?" (37 % prevalence, so always predicting benign
  scores 63 %; the two error types have very different costs.)

---

## Part C: PCA and eigenanalysis

**C1 ★ "Why is the covariance matrix PSD? Prove it in one line."**

* *Listen for:* vᵀSv = ‖X_c v‖²/(n − 1) ≥ 0. It is the sample variance of the projected data. It
  is singular when n − 1 < d or features are linearly dependent.

**C2 ★ "In what order does `eigh` return eigenvalues? Show me where you reorder the eigenvectors." (live probe)**

* *Listen for:* ascending order. Sort the eigenvalues descending **and** reorder the eigenvector
  *columns* with the same index array.
* *Red flags:* sorts eigenvalues but not vectors; reorders rows instead of columns; uses `eig`
  (complex output, no ordering guarantee).

**C3 "How many components keep 90 % of the variance? On which data did you fit PCA?"**

* *Should match (approximately):* breast cancer, standardised: **k = 7** (91.0 % on all rows,
  91.1 % on the reference training split; PC1 ≈ 0.44, PC2 ≈ 0.19). Iris, standardised: **k = 2**
  (72.96 % + 22.85 % = 95.8 %).
* *Red flags:* PCA fitted on train + test when a split is in use; cannot say how the test rows
  are projected.

**C4 "How do your eigenvalues relate to the singular values from your SVD route? Show me numerically."**

* *Listen for:* λⱼ = σⱼ²/(n − 1); the right singular vectors are the principal directions; Z = UΣ.
  Their numerical check should agree to about 10⁻¹⁴.

**C5 "Some of your eigh and SVD eigenvectors point in opposite directions. Is that a bug?"**

* *Listen for:* no. v and −v are both unit eigenvectors. For nearly repeated eigenvalues only the
  spanned subspace is determined, which is why comparisons should use subspaces (principal angles,
  projectors).

**C6 "What is your reconstruction error at k = 0 and at k = d?"**

* *Listen for:* at k = d it is zero (up to rounding). At k = 0 it is the total variance: a mean
  squared error of 1 per entry on z-scored training data. On the fitted data the error equals
  (n − 1)·Σ of the discarded eigenvalues.

**C7 "Why does scaling matter for PCA? What would PC1 be on raw breast-cancer features?"**

* *Listen for:* PCA maximises variance, which depends on units. On raw data PC1 is essentially
  "area" (worst area plus mean area) and explains about 98 % of the variance, purely because those
  values are in the hundreds to thousands.

---

## Part D: K-means (iris)

**D1 ★ "Why can neither step increase J? Why is the result still not guaranteed to be the global minimum?"**

* *Listen for:* the assignment step picks the nearest centroid for each point (the current choice
  is one of the options); the update step uses the mean, which minimises the within-cluster sum of
  squares. There are finitely many partitions, so it terminates. It is coordinate descent on a
  non-convex combinatorial problem, so it finds a local fixed point that depends on initialisation.

**D2 "Show me your distance computation. Is it vectorised? What shape is it?"**

* *Listen for:* an n × K matrix from broadcasting, or ‖x‖² − 2x·μ + ‖μ‖² (with clipping of tiny
  negative values).
* *Red flags:* a Python loop over points (slow, and the spec asks for vectorised operations); a
  library distance function used in place of their own computation.

**D3 ★ "What does your code do with an empty cluster? Make one happen." (live probe)**

* *Listen for:* a stated strategy (re-seed at the farthest or worst-fitted point, re-sample, or
  drop with a warning) and a justification. Probe: initialise one centroid far away (e.g. at
  [50, 50, 50, 50]) and run it.
* *Red flags:* `nan` centroids (the mean of an empty array), or a crash.

**D4 "Two of your runs gave different J. Which one do you report, and why?"**

* *Listen for:* local minima; use several restarts and keep the **lowest J**. That is an
  unsupervised criterion. Reference raw-feature minima: 78.85 (best), plus bad local minima at
  ≈ 142.75 and 145.53.
* *Red flags:* keeps the run with the best ARI against species, which uses the labels to select
  the model.

**D5 "How did you choose K?"**

* *Listen for:* either K = 3 stated as a given hyperparameter, or an unsupervised criterion on the
  features. The silhouette actually favours **K = 2** (setosa vs the rest); an honest student says so.
* *Red flags:* picked K by ARI or by the species count "because it matched best".

**D6 ★ "Was your ARI higher on raw or on standardised features? Why?"**

* *Should match (best of several starts):* raw K = 3: **J = 78.85, ARI = 0.730**; standardised
  (ddof = 0): **J = 139.82, ARI = 0.620**. With ddof = 1, J = 138.89 and the partitions are the same.
* *Listen for:* raw distances are dominated by petal length (variance about 3.1 cm²), which is also
  the most species-informative feature. Standardising gives the weak sepal-width feature equal
  weight. So "always standardise" is not automatically better.
* *Red flags:* standardised ARI higher than raw (check their scaling or initialisation); compares
  WCSS 78.85 and 139.82 directly.

**D7 "Why can't you use `accuracy_score(species, cluster_labels)`?"**

* *Listen for:* cluster IDs are arbitrary (J is invariant to relabelling). ARI is
  permutation-invariant and chance-corrected; accuracy would need an explicit matching step.

**D8 "After projecting to two principal components, your WCSS dropped. Is the clustering better?"**

* *Listen for:* not necessarily. Orthogonal projection can only shorten distances, and the dropped
  variance is gone. Compare WCSS/TSS, or evaluate both partitions in the same space. Reference:
  2-D keeps 95.8 % of the variance, ARI 0.620 → 0.601, and 2 points change cluster.

---

## Part E: Integrated pipeline

**E1 ★ "Point to every line where something is *fitted*. Which rows does each one see?" (live probe)**

* *Listen for:* scaler means and SDs, PCA mean, components and k, K-means centroids, λ, K: all from
  training rows only. `predict` and `transform` only read stored attributes.
* *Probe:* "Call `predict` on a single test row. Does anything change inside the object?"
* *Red flags:* `fit_transform` on the full data; PCA or K-means refitted inside `predict`;
  scikit-learn `PCA`, `KMeans` or `LogisticRegression` used inside `IntegratedMLPipeline`.

**E2 "How did you choose k for PCA and K for the distance features?"**

* *Listen for:* k from the 90 % rule on training data (reference: k = 7 on every split). K from an
  unsupervised criterion on the training PCA scores (the reference silhouette chooses K = 2), or
  fixed in advance.
* *Red flags:* K tuned on test metrics.

**E3 ★ "Your full pipeline beat (or lost to) the baseline. Is the difference real?"**

* *Listen for:* on 114 test cases, one prediction is 0.9 percentage points, so a single split
  rarely settles it. Look for repeated splits or CV with a spread. Reference over 20 splits: baseline
  0.972 ± 0.013, PCA 0.966 ± 0.018, full 0.959 ± 0.020; the full pipeline is worse in 17 of 20 splits.
  **A student who reports that the pipeline does not help has probably done it right.**

**E4 ★ "Compare κ₂ of your three design matrices. Why does PCA lower it, and why do the distance features raise it?"**

* *Listen for:* PCA scores are uncorrelated and centred (reference κ ≈ 4.5 against 329 for the
  30-feature baseline). Distances are partly linear in Z (R² ≈ 0.46 and 0.84 for K = 2), giving κ
  ≈ 8.5. If left uncentred they are nearly collinear with the intercept (κ ≈ 38).
* *Follow-up:* "Did your logistic regression converge on all three?" Uncentred distance features
  slowed gradient descent about tenfold in the reference (about 250k vs 23k iterations). Centring
  them with training means is an exact reparametrisation when the intercept is unpenalised.

**E5 "If you fit PCA on all the data but only use training labels, is that leakage?"**

* *Listen for:* yes. The test rows shape the representation (the reference's leaky PCA subspace
  rotated by about 10°). Even if the metric barely moves, the estimate is no longer of unseen-data
  performance.

**E6 "Did the distance features make the classes more linearly separable?"** (classification only)

* *Listen for:* an evidence-based answer, for example training errors of a lightly or
  unregularised model in each representation, or a separability check. Reference: separable in the
  30-D baseline, not certified in 7-D PCA (11 training errors), 10 errors with the distance features
  added: only a marginal gain.

---

## Part F and reproducibility

**F1 "PCA kept 91 % of the variance. Why did accuracy still drop?"**

* *Listen for:* variance is not class information. PCA never sees labels, and the discarded
  directions can contain the decision boundary (the 30-D training set is separable, but its 7-D
  projection is not).

**F2 "Explain the bias–variance effect of chaining PCA and K-means before the classifier."**

* *Listen for:* fewer parameters lowers estimation variance. The discarded information adds bias.
  The unsupervised stages are themselves estimated from data (local minima, split-to-split
  changes), which adds representation variance. They should cite their own repeated-split spread.

**F3 ★ "If I restart the kernel and run all, do I get exactly your numbers?" (live probe if time allows)**

* *Listen for:* fixed seeds for splits, initialisation and synthetic data. Local
  `np.random.default_rng(seed)` objects, or a single seeded global set at the top, are both fine.
* *Red flags:* numbers in the report that are not in the notebook; cells that only work when run
  out of order.

**F4 "What external code or AI assistance did you use, and where?"**

* *Listen for:* an answer consistent with their reproducibility statement and the course policy.

---

## Generic authenticity probes (any part)

Ask for a prediction *before* the student runs each change:

| Change | Expected effect |
|---|---|
| Remove the intercept column in Part A | Test RMSE rises sharply (the target mean is about 152, so predictions are forced through 0 when features are 0) |
| Replace `solve` with `inv` | Same answer at κ ≈ 20; the difference shows only on an ill-conditioned matrix |
| Set η = 3/λ_max for linear-regression GD | Diverges |
| Use `ddof=1` in the scaler | Every standardised feature shrinks by √((n−1)/n): WCSS scales by (n−1)/n, OLS coefficients by √(n/(n−1)); K-means partitions and OLS predictions are unchanged |
| Swap the positive class in Part B | Precision and recall change meaning; the weights flip sign; accuracy and AUC are unchanged |
| K = 2 on iris | Setosa vs the rest; silhouette rises and ARI falls |
| Fit the scaler on all rows | Tiny metric change on this data, but it is leakage |

Then pick one line of their code at random and ask what it does and why it is there.

---

## Reference values at a glance (seed 42; split-dependent unless noted)

| Part | Quantity | Reference |
|---|---|---|
| A | Diabetes train/test rows; design matrix | 353 / 89; 353 × 11, rank 11 |
| A | κ₂(X), κ₂(XᵀX) | 20.73, 429.9 |
| A | Test RMSE (normal equations = QR = GD) | 53.85 |
| B | Breast-cancer train/test rows | 455 / 114 (stratified) |
| B | Finite-difference max abs error | about 1e−10 |
| B | λ from 5-fold CV on training data | 0.001 |
| B | Test accuracy / precision / recall / F1 (malignant = 1, τ = 0.5) | 0.974 / 0.976 / 0.952 / 0.964 |
| C | k for ≥ 90 % (breast cancer, standardised) | 7 (91.1 % train; 91.0 % all rows) |
| C | Iris PC1 + PC2 | 72.96 % + 22.85 % = 95.81 % (all rows, not split-dependent) |
| D | Iris raw K = 3: J, ARI | 78.85, 0.730 (all rows) |
| D | Iris standardised K = 3: J, ARI | 139.82, 0.620 (all rows, ddof = 0) |
| D | Iris PCA 2-D K = 3: J, ARI | 115.19, 0.601 |
| E | Pipeline k, K | 7, 2 (training silhouette) |
| E | κ₂ baseline / PCA / full (centred D) | 328.7 / 4.5 / 8.5 |
| E | Mean test accuracy over 20 splits: baseline / PCA / full | 0.972 / 0.966 / 0.959 |
