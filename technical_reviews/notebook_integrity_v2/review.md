# Notebook input integrity v2 technical review

Status: ready for technical review only. This record is not advisor approval. The existing D3/D4 approval.json and SHA256SUMS.json files are preserved. D4 was running when this review began; no launch or resume was invoked here.

## Before-change comparison

D3 01 launcher: approved raw copy exists at the package checkpoint and matches approved SHA256 881d6e37d88aa81bfa0290755f42841a5b62f68c15289cf6e0613db756eb6e1f. Current code cell 1 changes total and active history formulas to include generations_per_batch. One read-only status-query code cell and one empty code cell were appended. Existing markdown and the other original code sources match. Outputs or execution counts changed in original cells 1, 3, 5, 7; notebook metadata changed. The appended status code is a real input change and cannot be treated as execution output.

D3 02 results: current raw SHA256 differs from the old approved ledger. No exact hash-matching approved copy was found. The available checkpoint matches the current raw file, so it cannot prove the old approved source. The current result notebook closes displayed figures and remains read-only.

D4 01 launcher: current raw SHA256 differs from the latest approved ledger after the user's notebook execution. No exact hash-matching approved copy was found. A pre-refresh checkpoint exists; relative to it, the source difference is the intentional generations_per_batch history-count correction. Original code-cell outputs/execution counts and notebook metadata changed after execution. The latest approved raw content cannot be reconstructed conclusively from that checkpoint alone.

D4 02 results: its raw SHA256 matches the current approved ledger. Its older checkpoint predates the figure display/close indentation fix; that older source is not the approved latest copy.

The D3 old ledger also differs from the shared experiments.py safety update, as well as its two dedicated notebooks. At review start the D4 old ledger differed only for its 01 launcher notebook. These are not silently re-approved.

## Versioned content rule

notebook-inputs-v1 hashes ordered cells, cell IDs, cell types, and exact joined sources for code, markdown, and raw cells. It also protects notebook format major version, kernelspec.name, language_info.name, launch_policy, and ordered cell tags. Kernel selection, the stated launch policy, and tags can affect how a notebook is run. Cell IDs make even a swap of two otherwise identical cells detectable.

Outputs, execution_count, cell execution timestamps, notebook display metadata, UI state, language_info.version, and nbformat minor version are ignored. A normal save after execution can therefore change those fields without changing the content digest. Source edits, new or removed cells, reordered cells, cell IDs, protected metadata, or tags change the digest. SHA256SUMS.json still pins non-notebook files byte-for-byte, including manifest, reference configuration, model code, calculation code, README, and the notebook-content manifest. Approval must bind package.json and SHA256SUMS.json; the notebook-content manifest is itself pinned by SHA256SUMS.json.

The revised verifier handles legacy packages with their original raw notebook hashes and accepts notebook-inputs-v1 only for a separately versioned package. It does not transfer any old approval to changed inputs. D4 still requires completed D3, its explicit review record, and an approval whose d3_review_sha256 matches that record. The new package approval.json files are intentionally absent.

## Read-only V2 draft inventory

Two student draft packages exist in student_packages/v2_draft_v1. They contain four assigned cases each. The central scenarios/v2_catalogue_draft_v1.json contains eight distinct physical scenario IDs, and the eight assigned IDs are unique. The separate nominal integration manifest contains one calculation condition. Thus two packages do not mean two physical scenarios. The V2 catalogue and parameter ranges remain draft and unapproved; no new scenarios were generated.

## Review scope

Inspect the revised shared student_package.py, notebook_content.py, each new package's package.json, SHA256SUMS.json, NOTEBOOK_CONTENT_SHA256.json, README.md, and dedicated 01/02 notebooks. The new packages are prepared for separate advisor approval; none may launch before an approval.json is issued against their exact hashes.

## Validation

The complete unittest suite ran with the openmc-proje WSL Conda Python and PYTHONPATH set to project src: 68 tests passed. The new temporary-directory tests mock launch and preflight, allow output-only saves, reject changed code/markdown/raw input, cell addition/deletion/reordering, protected metadata, manifest, model execution code, calculation profile, and attempts to rewrite content hashes without a new advisor approval. D4 review linkage is tested with a mocked D3 state. No Monte Carlo or launch/resume was executed. Both new packages pass verify(require_approval=False) and fail verify(require_approval=True) because approval.json is intentionally absent.
