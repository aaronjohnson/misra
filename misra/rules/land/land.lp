% land.lp: what the F12 deck's log adds up to.
%
% The log is a list of what happened, oldest first. These rules say which
% failures a later success has fixed, which are still open, what change most
% likely caused an open system failure, and one verdict for the whole log.
% Not loaded by the daemon (it reads rules/*.lp only): `misra land-log` runs it.
%
% Input facts (the deck writes them, one per log row):
%   entry(N, State, Kind, Repo).   N counts from 0, oldest first
%     State: ok | bad | info
%     Kind:  commit | push | bump | switch | check | ship | login | all | system
%     Repo:  a repo's name, or "system"

failed(N)    :- entry(N,bad,_,_).
succeeded(N) :- entry(N,ok,_,_).

% A system step: switching, or checking that ~/nixos builds and matches.
sys(N) :- entry(N,_,switch,_).
sys(N) :- entry(N,_,check,_).

% The same job on the same repo (a push of misra, say).
same(N,M) :- entry(N,_,K,R), entry(M,_,K,R), N != M, not sys(N).

% A failure is fixed by the next success at the same thing; for the system,
% by any later successful switch or check.
fixed_by(N,M) :- failed(N), succeeded(M), M > N, same(N,M).
fixed_by(N,M) :- failed(N), sys(N), succeeded(M), sys(M), M > N.
fixed(N) :- fixed_by(N,_).
first_fix(N,M) :- fixed_by(N,M), not fixed_by(N,L) : fixed_by(N,L), L < M.

open(N) :- failed(N), not fixed(N).

% Blame for an open system failure: the newest change landed before it.
change(C,R) :- succeeded(C), entry(C,_,commit,R).
change(C,R) :- succeeded(C), entry(C,_,bump,R).
newer_change(C,N) :- open(N), sys(N), change(C,_), change(D,_), C < D, D < N.
blame(N,R) :- open(N), sys(N), change(C,R), C < N, not newer_change(C,N).

% The verdict.
failures(F) :- F = #count { N : failed(N) }.
open_count(O) :- O = #count { N : open(N) }.
verdict(clear)  :- open_count(0).
verdict(open)   :- open_count(O), O > 0.

#show first_fix/2.
#show open/1.
#show blame/2.
#show failures/1.
#show open_count/1.
#show verdict/1.
