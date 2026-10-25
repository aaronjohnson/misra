% commands.lp: before Claude Code runs a shell command, should you be asked?
%
% Supply chain first: code fetched from a registry or a URL, outside code
% landing under ~ (which Claude Code trusts), and writes to the places a
% compromise hides (ssh keys, shell startup, autostart, Claude's own hooks).
% It can ask or deny, never allow: no conclusion means the normal prompts.
% Not loaded by the daemon; `misra check-command` runs it (the PreToolUse hook).
%
% Input facts (misra/commands.py):
%   seg(I). name(I, Cmd). arg(I, K, Word).   one simple command, prefixes unwrapped
%   pipe(I, J).          I's output goes into J
%   url(I).              an http(s) URL among I's arguments
%   procsub(I).          I runs inside <( ), its output read as a file
%   script_file(I).      I names a script file (x.py, x.sh …) to run
%   flake(I, Where).     a flake reference: nixpkgs | local | remote
%   clone_to(I, Where).  git clone's destination: home | outside
%   writes(I, Place).    a redirect or tee: ssh | shell_rc | claude | autostart | home | outside
%   cwd_in_home.

has(I,A) :- arg(I,_,A).

downloader(I) :- name(I,"curl").
downloader(I) :- name(I,"wget").
downloader(I) :- name(I,"fetch").

% An interpreter runs what arrives on stdin unless it was given its own code:
% `curl … | python3 -c '…'` parses data, `curl … | python3` runs the download.
runs_code(I) :- name(I,S), interpreter(S), not own_code(I).
own_code(I) :- has(I,"-c").
own_code(I) :- has(I,"-e").
own_code(I) :- script_file(I).
interpreter("sh"). interpreter("bash"). interpreter("zsh"). interpreter("dash"). interpreter("fish").
interpreter("python"). interpreter("python3"). interpreter("perl"). interpreter("ruby").
interpreter("node"). interpreter("deno"). interpreter("bun"). interpreter("sudo"). interpreter("source").

% ---- deny: no prompt is enough ----
deny(pipe_to_shell) :- pipe(I,J), downloader(I), runs_code(J).
deny(download_run)  :- procsub(I), downloader(I).

% ---- ask: code from a registry or the network ----
js("npm";"pnpm";"yarn";"bun").
js_install_verb("install";"i";"add";"ci";"update";"upgrade").
ask(js_install) :- name(I,M), js(M), has(I,V), js_install_verb(V).
ask(js_install) :- name(I,"yarn"), not has(I,_).                     % bare `yarn` installs
ask(js_run_fresh) :- name(I,"npx").
ask(js_run_fresh) :- name(I,"bunx").
ask(js_run_fresh) :- name(I,"pnpx").
ask(js_run_fresh) :- name(I,M), js(M), has(I,"dlx").
ask(js_run_fresh) :- name(I,"npm"), has(I,"exec").

ask(pip_install) :- name(I,P), pip(P), has(I,"install").
pip("pip";"pip3";"pipx").
ask(pip_install) :- name(I,"uv"), has(I,"pip"), has(I,"install").
ask(pip_install) :- name(I,"uv"), has(I,"tool"), has(I,"install").
ask(pip_install) :- name(I,"uvx").
ask(pip_install) :- name(I,Py), py(Py), has(I,"-m"), has(I,"pip"), has(I,"install").
py("python";"python3").

ask(cargo_install) :- name(I,"cargo"), has(I,"install").
ask(go_install)    :- name(I,"go"), has(I,"install").
ask(gem_install)   :- name(I,"gem"), has(I,"install").
ask(mix_install)   :- name(I,"mix"), has(I,"archive.install").
ask(mix_install)   :- name(I,"mix"), has(I,"escript.install").

ask(nix_remote)  :- name(I,"nix"), flake(I,remote).
ask(nix_profile) :- name(I,"nix"), has(I,"profile"), has(I,"install").
ask(nix_profile) :- name(I,"nix"), has(I,"profile"), has(I,"add").
ask(nix_profile) :- name(I,"nix-env"), has(I,"-i").
ask(nix_profile) :- name(I,"nix-env"), has(I,"-iA").

% ---- ask: outside code under ~ ----
ask(clone_in_home) :- clone_to(_,home).

% ---- ask: where a compromise hides ----
ask(writes_ssh)       :- writes(_,ssh).
ask(writes_shell_rc)  :- writes(_,shell_rc).
ask(writes_claude)    :- writes(_,claude).
ask(writes_autostart) :- writes(_,autostart).

decision(deny) :- deny(_).
decision(ask)  :- ask(_), not decision(deny).

#show decision/1.
#show deny/1.
#show ask/1.
