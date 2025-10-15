{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem
      (system:
        let
          pkgs = import nixpkgs {
            inherit system;
          };

          python = pkgs.python312;
        in
        {
          devShell = pkgs.mkShell
            {
              LD_LIBRARY_PATH = "${pkgs.stdenv.cc.cc.lib}/lib";
              PYO3_PYTHON = "${python}/bin/python";
              RUST_SRC_PATH = "${pkgs.rust.packages.stable.rustPlatform.rustLibSrc}";

              buildInputs = with pkgs; [
                bashInteractive
                black
                cargo
                clippy
                glibcLocales
                go
                kind
                kubernetes-helm
                patchutils
                pre-commit
                python.pkgs.tox
                python.pkgs.uv
                renovate
                rust-analyzer
                rustc
                rustfmt
              ];
            };
        }
      );
}
