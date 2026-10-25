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

    weather = {
      enable = lib.mkEnableOption ''
        local weather for the sky rules (is it a grey day?), fetched from
        Open-Meteo every 15 minutes by a separate unprivileged unit, so the
        daemon itself never gets network access'';
      locationFile = lib.mkOption {
        type = lib.types.str;
        default = "/var/lib/misra/weather.toml";
        description = ''
          TOML file with `latitude` and `longitude` (city-level is enough; they
          are rounded to two decimals before sending). Deliberately not managed
          by Nix, like configFile: where you live stays out of the store and out
          of any public configuration repository. The weather unit gets only
          this file, as a systemd credential.
        '';
      };
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

    # The weather, for rules/sky.lp. Its own unit so the daemon keeps no network:
    # a throwaway user, internet only, writing one file the daemon reads.
    systemd.services.misra-weather = lib.mkIf cfg.weather.enable {
      description = "misra: save the local weather for the sky rules";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      # No location yet (ops/weather-location writes it): skip quietly, don't fail.
      unitConfig.ConditionPathExists = cfg.weather.locationFile;
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${lib.getExe cfg.package} weather /run/misra-weather/now.json";
        LoadCredential = "location:${cfg.weather.locationFile}";
        # A fixed system user, not DynamicUser: DynamicUser hides its directory behind
        # /run/private (0700), where the daemon, root with no capabilities, can't read it.
        User = "misra-weather";
        Group = "misra-weather";
        RuntimeDirectory = "misra-weather";
        RuntimeDirectoryMode = "0755";
        RuntimeDirectoryPreserve = true;   # keep the last reading between runs
        ProtectSystem = "strict";
        ProtectHome = true;
        PrivateTmp = true;
        PrivateDevices = true;
        NoNewPrivileges = true;
        CapabilityBoundingSet = "";
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectControlGroups = true;
        ProtectClock = true;
        ProtectHostname = true;
        RestrictAddressFamilies = [ "AF_INET" "AF_INET6" "AF_UNIX" ];   # AF_UNIX: DNS through resolved
        RestrictNamespaces = true;
        RestrictRealtime = true;
        LockPersonality = true;
        MemoryDenyWriteExecute = true;
        SystemCallArchitectures = "native";
        Nice = 10;
      };
    };
    users.users.misra-weather = lib.mkIf cfg.weather.enable {
      isSystemUser = true;
      group = "misra-weather";
      description = "misra weather fetcher";   # no colons: it's a passwd field
    };
    users.groups.misra-weather = lib.mkIf cfg.weather.enable { };

    systemd.timers.misra-weather = lib.mkIf cfg.weather.enable {
      description = "Fetch the weather for misra every 15 minutes";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "1min";
        OnUnitActiveSec = "15min";
        RandomizedDelaySec = "1min";
      };
    };

    # Check straight away after waking, rather than at the next tick.
    systemd.services.misra-resume = {
      description = "Ask misra to check after a resume";
      wantedBy = sleepTargets;
      after = sleepTargets;
      serviceConfig = {
        Type = "oneshot";
        ExecStart = [ "${pkgs.systemd}/bin/systemctl kill --signal=USR1 --kill-whom=main misra.service" ]
          ++ lib.optional cfg.weather.enable "-${pkgs.systemd}/bin/systemctl start --no-block misra-weather.service";
      };
    };

    systemd.user.services.misra-notify = lib.mkIf cfg.notify {
      description = "Show new misra alerts";
      # the system profile too: makoctl, to draw the alert chart in the cards' light/dark colours
      path = [ pkgs.libnotify "/run/current-system/sw" ];
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
