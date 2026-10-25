{ lib, python3Packages, git }:

python3Packages.buildPythonApplication {
  pname = "misra";
  version = "0.7.1";
  pyproject = true;

  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [ ../pyproject.toml ../misra ../tests ];
  };

  build-system = [ python3Packages.setuptools ];
  dependencies = [ python3Packages.clingo python3Packages.pillow ];
  nativeCheckInputs = [ python3Packages.pytestCheckHook git ];   # git: test_release makes throwaway repos

  meta = {
    description = "Cross-checks a laptop's sensors with logic rules";
    license = lib.licenses.mit;
    mainProgram = "misra";
  };
}
