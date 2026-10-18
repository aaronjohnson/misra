% power.lp: which power sensors to believe.
%
% Several sensors each claim something about three properties of the world:
%   ac       on | off                        is a charger supplying power?
%   battery  present | absent
%   flow     charging | discharging | idle   what the battery is doing
%
% A sensor is either working, so everything it claims is true, or abnormal
% (ab), so its claims say nothing. We look for the true state plus the
% fewest, least trusted abnormal sensors that explain every claim together.
% This is consistency-based diagnosis: no branching code, just what a
% healthy sensor implies and what the physics allows.
%
% Input facts (from the collectors):
%   sensor(S).  trust(S, W).          W: cost of blaming S alone (higher = more trusted)
%   claim(S, Prop, Value).
%   reading(S, pct, Percent).         charge level, if S reports one
%   acpi_error(Kind, Device, Method). an ACPI method failed since the last resume
%   acpi_unreadable(Kind).            a sysfs read that runs firmware code failed
%   derived_from(S, Source).          S is computed from Source's readings

prop(ac;battery;flow).
value(ac,(on;off)).
value(battery,(present;absent)).
value(flow,(charging;discharging;idle)).

% Exactly one true value for each property.
1 { truth(P,V) : value(P,V) } 1 :- prop(P).

% A sensor can fail on its own (a guess, paid for by its trust)...
{ ab_own(S) } :- sensor(S).
ab(S) :- ab_own(S).

% ...or because something it depends on broke. The ACPI battery and adapter
% reports both run firmware (AML) methods, and the USB-C driver (ucsi_acpi)
% reaches the EC through ACPI too, so one firmware fault can corrupt all
% three at once. Blaming the shared cause once is cheaper than blaming each.
cause(acpi_bat,firmware). cause(acpi_ac,firmware). cause(ucsi,firmware).
cause_trust(firmware,3).
{ broken(C) } :- cause(_,C).
ab(S) :- cause(S,C), broken(C), sensor(S).

% A sensor that isn't abnormal must be telling the truth.
:- claim(S,P,V), not ab(S), not truth(P,V).

% Physics. The machine is running, so something powers it.
:- truth(ac,off), truth(battery,absent).
% No charger: the battery must be the one supplying power.
:- truth(ac,off), not truth(flow,discharging).
% No battery: nothing can flow into or out of it.
:- truth(battery,absent), not truth(flow,idle).

% Observed evidence, not guesses (so it costs nothing): a firmware method
% behind the sensor is failing.
acpi_sensor(battery,acpi_bat).
acpi_sensor(adapter,acpi_ac).
ab(S) :- acpi_error(K,_,_), acpi_sensor(K,S), sensor(S).
ab(S) :- acpi_unreadable(K), acpi_sensor(K,S), sensor(S).
broken(firmware) :- acpi_error(K,_,_), acpi_sensor(K,_).
broken(firmware) :- acpi_unreadable(K), acpi_sensor(K,_).

% A sensor computed from another one can't be better than its source.
ab(S) :- derived_from(S,T), ab(T).

% Trust works like a cost: roughly how unlikely a failure is. Pick the
% cheapest set of guesses that explains everything.
#minimize { W@1,S,own : ab_own(S), trust(S,W) ; W@1,C,cause : broken(C), cause_trust(C,W) }.

% ---- Conclusions ----

% How many working sensors back each true value.
support(P,V,N) :- truth(P,V), N = #count { S : claim(S,P,V), not ab(S) }.

% The charge level to show: from the most trusted working sensor that has one.
pct_candidate(S) :- reading(S,pct,_), not ab(S).
best_pct_trust(W) :- W = #max { T,S : pct_candidate(S), trust(S,T) }, pct_candidate(_).
shown_pct(V,S) :- pct_candidate(S), trust(S,W), best_pct_trust(W), reading(S,pct,V).

faulty(S) :- ab(S).
blamed(C) :- broken(C).
power_ok :- not faulty(_).

#show truth/2.
#show faulty/1.
#show blamed/1.
#show support/3.
#show shown_pct/2.
#show power_ok/0.
