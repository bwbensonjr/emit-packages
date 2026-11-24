# Spec Delta

## Purpose

Defines the public binding surface of the `(malt learner)` facade: which base Scheme
names it replaces with dual-aware versions, and how it composes with implicit and
explicit `(scheme base)` imports.

## ADDED Requirements

### Requirement: Facade exports dual-aware ordering comparators
`(malt learner)` SHALL export `=`, `<`, `<=`, `>`, and `>=` bound to the same
procedures as `=-0-0`, `<-0-0`, `<=-0-0`, `>-0-0`, and `>=-0-0`. Each compares the
primal values of its two arguments, accepting plain real numbers and scalar duals in
any combination, and returns a boolean.

#### Scenario: Comparing a differentiable arithmetic result
- **WHEN** a program imports `(malt learner)` and evaluates `(< (- 13 4) 4)`
- **THEN** the result is `#f` and no "not a number" error is raised

#### Scenario: Recursive numeric code after importing the facade
- **WHEN** a program or REPL session imports `(malt learner)`, defines
  `(define (rem x y) (if (< x y) x (rem (- x y) y)))`, and evaluates `(rem 13 4)`
- **THEN** the result's primal value is `1`

#### Scenario: Binding identity with the base-rank comparators
- **WHEN** a program imports `(malt learner)` and evaluates `(eq? < <-0-0)`
- **THEN** the result is `#t`, and likewise for `=`, `<=`, `>`, and `>=`

#### Scenario: Comparing plain numbers
- **WHEN** a program imports `(malt learner)` and evaluates `(<= 2 3)` and `(= 2.0 3.0)`
- **THEN** the results are `#t` and `#f`

### Requirement: Facade exports dual-aware sign predicates
`(malt learner)` SHALL export `zero?`, `positive?`, and `negative?`, each accepting a
plain real number or a scalar dual and answering the base predicate on its primal
value.

#### Scenario: Testing a dual for zero
- **WHEN** a program imports `(malt learner)` and evaluates `(zero? (- 4 4))`
- **THEN** the result is `#t` and no "not a number" error is raised

#### Scenario: Sign of a dual
- **WHEN** a program imports `(malt learner)` and evaluates `(positive? (- 4 3))` and
  `(negative? (- 4 3))`
- **THEN** the results are `#t` and `#f`

### Requirement: Facade composes with explicit base imports by exclusion
A program that imports `(scheme base)` explicitly together with the unprefixed
facade SHALL be rejected with an import-conflict diagnostic unless it excludes every
base name the facade exports, and SHALL compile when it excludes them.

#### Scenario: Excluding only the arithmetic names
- **WHEN** a program imports `(except (scheme base) + - * / abs max expt)` and
  `(malt learner)`
- **THEN** compilation fails with a diagnostic naming a conflict

#### Scenario: Excluding every overlapping name
- **WHEN** a program imports
  `(except (scheme base) + - * / abs max expt = < <= > >= zero? positive? negative?)`
  and `(malt learner)` and evaluates `(gradient (lambda (x) (* x x)) 3.0)`
- **THEN** the program runs and the result is `6.0`

### Requirement: Comparators are not differentiable
The facade comparators and sign predicates SHALL return booleans and SHALL NOT
contribute to gradients; the tensorized comparators `=-1 <-1 >-1 <=-1 >=-1 !=-1`
SHALL remain available under those names with their existing behavior.

#### Scenario: Branching inside a differentiated function
- **WHEN** a program evaluates
  `(gradient (lambda (x) (if (< x 0) (- 0 x) x)) 3.0)`
- **THEN** the result is `1.0`

#### Scenario: Tensorized comparator unchanged
- **WHEN** a program evaluates `(<-1 (tensor 1.0 5.0) (tensor 2.0 2.0))`
- **THEN** the result is a tensor equal to `(tensor 1.0 0.0)`
