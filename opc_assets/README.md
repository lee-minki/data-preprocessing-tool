# OPC assets

This directory contains standalone OPC tag-search assets for the preprocessing portal/local backend.

- `tag_index/*.jsonl` is generated from `RiMSproj_SD_Monitoring_System/src/narae_rims_ax/data/tags.CSV`.
- The full source CSV is intentionally not required at runtime for search/current-value lookup because each JSONL row includes `fulltagname`, `utagid`, `plant`, `sourcename`, `tagname`, `description`, and `units`.
- Regenerate indexes with:

```bash
python3 -m preprocessing_portal.tag_index build \
  --tags-csv /path/to/tags.CSV \
  --output-dir opc_assets/tag_index
```

Included prefixes: `PJ1`, `PJ2`, `KY`, `HN`, `WR`, `YJ`.
