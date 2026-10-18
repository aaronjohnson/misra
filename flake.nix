{
  description = "misra: cross-checks a laptop's sensors with logic rules";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      lib = nixpkgs.lib;
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAll = f: lib.genAttrs systems (s: f nixpkgs.legacyPackages.${s});
    in
    {
      packages = forAll (pkgs: { default = pkgs.callPackage ./nix/package.nix { }; });

      # Building the package runs the tests.
      checks = forAll (pkgs: { default = self.packages.${pkgs.stdenv.hostPlatform.system}.default; });

      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = [ (pkgs.python3.withPackages (p: [ p.clingo p.pytest ])) pkgs.clingo ];
        };
      });

      nixosModules.default = { pkgs, ... }: {
        imports = [ ./nix/module.nix ];
        services.misra.package = lib.mkDefault self.packages.${pkgs.stdenv.hostPlatform.system}.default;
      };
    };
}
