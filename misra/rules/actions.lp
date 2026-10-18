% actions.lp: what to do about the conclusions. Edge-triggered: the daemon
% passes last tick's conclusions in as was(Atom), so alerts fire when
% something changes, not on every tick.
%
% Input facts:
%   was(Atom).               a conclusion that held for certain last tick
%   resumed(Kind).           woke from suspend | hibernate since the last tick
%   first_tick.              the daemon just started

% ---- Power ----
alert(power_fault,S)     :- faulty(S), not was(faulty(S)).
alert(power_recovered,S) :- was(faulty(S)), not faulty(S).

% A new fault gets the full capture: firmware tables, EC, kernel log.
capture(deep,power_fault) :- alert(power_fault,_).

% ---- Links ----
alert(link_at_risk,P)  :- problem(P), not was(problem(P)), not first_tick.
alert(link_down)       :- link_state(down), not was(link_state(down)), not first_tick.
alert(link_back)       :- link_state(ok), was(link_state(down)).
alert(fallback,L)      :- advise(prepare_fallback,L), not was(advise(prepare_fallback,L)).
alert(hotspot,L)       :- advise(enable_hotspot,L), not was(advise(enable_hotspot,L)).

% ---- Resume ----
% Every resume gets a light snapshot (just the facts and conclusions) so a
% bad resume can be compared with good ones.
capture(light,resume) :- resumed(_).
alert(after_resume,K)  :- resumed(K), faulty(_).

#show alert/1.
#show alert/2.
#show capture/2.
