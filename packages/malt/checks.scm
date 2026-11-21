;;; Execution-path checks for Malt. See the checks.scm contract in the top-level README.
((check malt-core       (program "tests/core.scm")       (expect "(malt-core-complete 120)"))
 (check malt-training   (program "tests/training.scm")   (expect "(malt-training 82)"))
 (check malt-direct     (program "tests/direct.scm")     (expect "(malt-direct 6.0)"))
 (check malt-unprefixed (program "tests/unprefixed.scm") (expect "(malt-unprefixed 6.0)"))
 (check malt-notation   (program "tests/notation.scm")   (expect "(malt-notation 48)"))
 (check malt-xor        (program "tests/xor.scm")        (expect "(malt-xor-complete ok)")))
