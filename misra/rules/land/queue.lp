% queue.lp: where the deck stands, said by rules rather than a fixed string.
%
% Input facts (the deck, alongside the log's entry/4):
%   queued(K, Label, Repo).    a step still to run, K in the deck's order
%   skipped(K, Label, Repo).   a step N'd for this opening
%   switch(State).             same | differs | broken | checking
%   dirty(Repo, N).  behind(Repo, N).  stale_draft(Repo).
%   busy.  loading.

waiting :- queued(_,_,_).
skipped_any :- skipped(_,_,_).

status(running)       :- busy.
status(reading)       :- loading, not busy.
status(next)          :- waiting, not busy, not loading.
idle :- not busy, not loading, not waiting.
status(checking)      :- idle, switch(checking).
status(broken)        :- idle, switch(broken).
status(skipped_only)  :- idle, skipped_any, not switch(checking), not switch(broken).
status(clear)         :- idle, not skipped_any, not switch(checking), not switch(broken).

% What a quiet deck should still mention: work that land and ship won't touch.
note(unstaged,R,N)  :- dirty(R,N), N > 0.
note(behind,R,N)    :- behind(R,N), N > 0.
note(stale_draft,R) :- stale_draft(R).
note(running_matches) :- switch(same).

% Today's tally from the log: steps that held.
done(D) :- D = #count { N : entry(N,ok,K,_), K != system, K != check }.

#show status/1.
#show note/3.
#show note/2.
#show note/1.
#show done/1.
#show skipped/3.
