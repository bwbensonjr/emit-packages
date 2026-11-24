;; Dual-aware comparators and sign predicates exported by the learner facade.
;; Uses the implicit base, like direct.scm, so the facade's names win.
(import (scheme write) (malt learner))

(define passed '())
(define (check name ok)
  (if (not ok) (error "comparator check failed" name))
  (set! passed (cons name passed)))

;; The reported program: base `<` rejected the dual that learner `-` returns.
(define (remainder x y)
  (if (< x y)
      x
      (remainder (- x y) y)))
(check 'remainder (eqv? (primal (remainder 13 4)) 1))
(check 'less-than-dual (eq? (< (- 13 4) 4) #f))

;; The facade names are the base-rank comparators, not copies.
(check 'identity-= (eq? = =-0-0))
(check 'identity-< (eq? < <-0-0))
(check 'identity-<= (eq? <= <=-0-0))
(check 'identity-> (eq? > >-0-0))
(check 'identity->= (eq? >= >=-0-0))

(check 'plain-<= (eq? (<= 2 3) #t))
(check 'plain-= (eq? (= 2.0 3.0) #f))

(check 'zero-dual (eq? (zero? (- 4 4)) #t))
(check 'positive-dual (eq? (positive? (- 4 3)) #t))
(check 'negative-dual (eq? (negative? (- 4 3)) #f))

;; Comparators branch inside a differentiated function without contributing.
(define (absolute x) (if (< x 0) (- 0 x) x))
(check 'gradient-positive-branch (= (gradient absolute 3.0) 1.0))
(check 'gradient-negative-branch (= (gradient absolute -3.0) -1.0))

;; The tensorized comparators keep their names and behavior.
(check 'tensorized-<-1
       (equal? (tensor->vector (<-1 (tensor 1.0 5.0) (tensor 2.0 2.0))) #(1.0 0.0)))

(write (list 'malt-comparators (length passed)))
(newline)
