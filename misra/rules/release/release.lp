% release.lp: should ~/nixos take this repo at a release tag, or at its branch tip?
%
% A tag is a checkpoint: named, signed, and something to roll back to. The
% CHANGELOG decides the name: its newest heading's version (misra's "## 0.6.0 · …").
% Not loaded by the daemon; `misra release-plan REPO` runs it at land's Bump step.
%
% Input facts (misra/release.py):
%   want_tag(T).    "v" + the CHANGELOG's newest version, when it has one
%   tag(T).         a tag that exists
%   head_tag(T).    a tag on the commit being pushed

plan(new_tag) :- want_tag(T), not tag(T).        % a new version: tag it, take the tag
plan(at_tag)  :- want_tag(T), head_tag(T).       % already tagged here: take the tag
% Tagged, but commits have come since and the CHANGELOG wasn't bumped: don't
% move a tag (it's a checkpoint), stay on the tip and say so.
plan(stale)   :- want_tag(T), tag(T), not head_tag(T).
plan(tip)     :- not want_tag(_).                % no versions in this CHANGELOG

mode(tag) :- plan(new_tag).
mode(tag) :- plan(at_tag).
mode(tip) :- plan(stale).
mode(tip) :- plan(tip).

#show plan/1.
#show mode/1.
