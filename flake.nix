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
        in
        {
          devShell = pkgs.mkShell
            {
              LD_LIBRARY_PATH = "${pkgs.stdenv.cc.cc.lib}/lib";
              RUST_SRC_PATH = "${pkgs.rust.packages.stable.rustPlatform.rustLibSrc}";

              buildInputs = with pkgs; [
                bashInteractive
                black
                cargo
                clippy
                glibcLocales
                kind
                kubernetes-helm
                patchutils
                python311Packages.tox
                renovate
                rust-analyzer
                rustc
                rustfmt
                uv
              ];
            };
        }
      );
}
