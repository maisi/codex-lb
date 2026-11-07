use std::path::Path;
use std::process::Command;

#[test]
fn resolved_workspace_graph_excludes_unmaintained_pin_utils() {
    let workspace = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let output = Command::new(env!("CARGO"))
        .current_dir(workspace)
        .args([
            "metadata",
            "--locked",
            "--all-features",
            "--format-version",
            "1",
        ])
        .output()
        .expect("run cargo metadata for the resolved workspace graph");
    assert!(
        output.status.success(),
        "cargo metadata failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );

    let metadata: serde_json::Value =
        serde_json::from_slice(&output.stdout).expect("decode cargo metadata");
    let packages = metadata["packages"].as_array().expect("resolved packages");
    assert!(
        !packages
            .iter()
            .any(|package| package["name"] == "pin-utils"),
        "resolved workspace graph must exclude pin-utils (RUSTSEC-2026-0441)"
    );
}
