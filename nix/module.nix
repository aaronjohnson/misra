{ config, lib, pkgs, ... }:

let
  cfg = config.services.misra;
  sleepTargets = [ "suspend.target" "hibernate.target" "hybrid-sleep.target" "suspend-then-hibernate.target" ];
in
{
  options.services.misra = {
    enable = lib.mkEnableOption "misra, which cross-checks power and network sensors";

    package = lib.mkOption {
      type = lib.types.package;
      description = "The misra package.";
    };

    interval = lib.mkOption {
      type = lib.types.ints.positive;
      default = 30;
      description = "Seconds between checks. It also checks right after every resume.";
    };

    configFile = lib.mkOption {
      type = lib.types.str;
      default = "/var/lib/misra/local.toml";
      description = ''
        TOML file naming your uplinks (see docs/links.md). Deliberately not
        managed by Nix: it names your networks, so it stays out of the Nix
        store and out of any public configuration repository.
      '';
    };

    notify = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Show alerts as desktop notifications (notify-send) for logged-in users.";
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ cfg.package ];

    systemd.services.misra = {
      description = "misra: cross-check power and network sensors";
      wantedBy = [ "multi-user.target" ];
      after = [ "NetworkManager.service" ];
      path = with pkgs; [ iw networkmanager systemd fw-ectool framework-tool upower coreutils gnugrep bash ];
      serviceConfig = {
        ExecStart = "${lib.getExe cfg.package} --config ${cfg.configFile} daemon --interval ${toString cfg.interval}";
        Restart = "on-failure";
        RestartSec = 10;
        StateDirectory = "misra";
        StateDirectoryMode = "0750";
        RuntimeDirectory = "misra";
        RuntimeDirectoryMode = "0755";
        # Root only to read the EC (/dev/cros_ec) and the firmware tables, both
        # owned by root. No capabilities, nothing writable outside its own dirs.
        CapabilityBoundingSet = "";
        DevicePolicy = "closed";
        DeviceAllow = [ "/dev/cros_ec rw" ];
        ProtectSystem = "strict";
        ProtectHome = true;
        PrivateTmp = true;
        NoNewPrivileges = true;
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectControlGroups = true;
        ProtectClock = true;
        ProtectHostname = true;
        RestrictAddressFamilies = [ "AF_UNIX" "AF_NETLINK" ];
        RestrictNamespaces = true;
        RestrictRealtime = true;
        LockPersonality = true;
        MemoryDenyWriteExecute = true;
        SystemCallArchitectures = "native";
        Nice = 10;
      };
    };

    # Check straight away after waking, rather than at the next tick.
    systemd.services.misra-resume = {
      description = "Ask misra to check after a resume";
      wantedBy = sleepTargets;
      after = sleepTargets;
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${pkgs.systemd}/bin/systemctl kill --signal=USR1 --kill-whom=main misra.service";
      };
    };

    systemd.user.services.misra-notify = lib.mkIf cfg.notify {
      description = "Show new misra alerts";
      path = [ pkgs.libnotify ];
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${lib.getExe cfg.package} notify";
      };
    };

    systemd.user.paths.misra-notify = lib.mkIf cfg.notify {
      description = "Watch for misra alerts";
      wantedBy = [ "default.target" ];
      pathConfig.PathChanged = "/run/misra/alerts.json";
    };
  };
}
