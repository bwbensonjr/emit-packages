;;; Package metadata for Malt, read by the collection's tools.
(package
  (name malt)
  (version "0.1.0")
  (summary "Tensors, reverse-mode automatic differentiation, and training utilities from The Little Learner")
  (license "MIT")
  (emit (minimum "0.10.0"))
  (upstream "https://github.com/themetaschemer/malt" "92a3e63aebf8f0801cffdb6b8a44c199d7973148")
  (libraries
    (malt learner)
    (malt learner autodiff)
    (malt learner diagnostics)
    (malt learner formatting)
    (malt learner hyperparameters)
    (malt learner operations)
    (malt learner random)
    (malt learner recording)
    (malt learner tensors)
    (malt learner training)))
