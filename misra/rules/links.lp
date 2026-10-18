% links.lp: how healthy is the network link, and what's the next one to use?
%
% Observes only. It advises (and the daemon notifies); it never switches.
%
% Input facts:
%   link_up(wifi).                    associated to an access point
%   internet(State).                  full | limited | portal | none | unknown
%   active(Label).                    the configured uplink in use, if any
%   uplink(Label, Role).              configured: mlo | wifi | starlink | phone_bt | phone_hotspot
%   visible(Label).                   seen in the last Wi-Fi scan (or paired and reachable)
%   mlo_links(N).                     links in the current multi-link association
%   signal(Dbm).                      now
%   signal_then(Dbm).                 about five minutes ago
%   event(Kind, Age, N).              N numbers the events; Age in seconds; Kind: assoc | drop_remote |
%                                     drop_local | beacon_loss | handshake_timeout
%   counter(Name, Delta).             since the last tick: beacon_loss, tx_failed

% ---- How is the link? ----

roam_burst :- #count { N : event(assoc,A,N), A <= 300 } >= 3.
dropping   :- #count { N : event(drop_remote,A,N), A <= 900 } >= 2.
dropping   :- #count { N : event(handshake_timeout,A,N), A <= 900 } >= 2.
beacons_lost :- counter(beacon_loss,D), D >= 3.
weak       :- signal(S), S < -75.
fading     :- signal(N), signal_then(T), T - N >= 10, N < -67.

% An MLO association running on fewer links than it should.
expect_mlo    :- active(L), uplink(L,mlo).
mlo_degraded  :- expect_mlo, link_up(wifi), mlo_links(N), N < 2.

problem(roam_burst)   :- roam_burst.
problem(dropping)     :- dropping.
problem(beacons_lost) :- beacons_lost.
problem(weak)         :- weak.
problem(fading)       :- fading.
problem(mlo_degraded) :- mlo_degraded.
problem(no_internet)  :- link_up(wifi), internet(none).
problem(no_internet)  :- link_up(wifi), internet(limited).

link_state(down)     :- not link_up(wifi).
link_state(at_risk)  :- link_up(wifi), problem(_).
link_state(ok)       :- link_up(wifi), not problem(_).

% ---- What to fall back to ----

% Lower rank is preferred: a parked Starlink costs no mobile data; Bluetooth
% tethering can stay up beside Wi-Fi; the phone's Wi-Fi hotspot replaces it.
role_rank(mlo,0). role_rank(wifi,0).
role_rank(starlink,1). role_rank(phone_bt,2). role_rank(phone_hotspot,3).

fallback(L,R) :- uplink(L,Role), role_rank(Role,R), R > 0, visible(L), not active(L).
best_rank(R)  :- R = #min { R2,L : fallback(L,R2) }, fallback(_,_).
best_fallback(L) :- fallback(L,R), best_rank(R).

needs_fallback :- link_state(at_risk).
needs_fallback :- link_state(down).

advise(prepare_fallback,L)   :- needs_fallback, best_fallback(L).
advise(enable_hotspot,L)     :- needs_fallback, not fallback(_,_),
                                uplink(L,phone_hotspot), not visible(L).
advise(no_fallback)          :- needs_fallback, not fallback(_,_),
                                not uplink(_,phone_hotspot).

#show link_state/1.
#show problem/1.
#show advise/2.
#show advise/1.
#show fallback/2.
