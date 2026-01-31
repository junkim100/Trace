# Changelog

All notable changes to Trace will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-02-01

### Added
- First stable release of Trace

### Fixed
- Window no longer steals focus when toggled via keyboard shortcut (Cmd+Shift+T)
- Summarizer now works correctly even when event capture misses foreground app changes
- Improved keyframe selection using visual diff scores as fallback

## [0.9.12] - 2026-01-31

### Fixed
- Trace window stealing focus from other apps during keyboard shortcuts
- Summarizer failing when events don't match screenshots
- Idle detection hints now consider screenshot count

## [0.9.11] - 2026-01-31

### Added
- Daily backfill support via backfill button

### Fixed
- None duration bug causing crashes in daily revision

## [0.9.10] - 2026-01-29

### Fixed
- Reverted aggressive screenshot deletion for skipped hours
- Screenshots now preserved when hours are marked as idle

## [0.9.9] - 2026-01-29

### Fixed
- Screenshot retention for idle hours
- Bidirectional notes sync between filesystem and database

## [0.9.7] - 2026-01-28

### Fixed
- Note creation issues
- Updated LLM models

## [0.9.6] - 2026-01-28

### Added
- Content validation for generated notes
- Periodic filesystem sync

## [0.9.5] - 2026-01-28

### Added
- Force reprocess option for backfill

### Fixed
- Backfill timeout issues

## [0.9.4] - 2026-01-28

### Fixed
- Service manager not initialized error

## [0.9.3] - 2026-01-28

### Added
- Auto-sync filesystem with database
- Manual backfill button in UI

## [0.9.2] - 2026-01-28

### Fixed
- Web search functionality
- Auto-reindex for orphaned notes

## [0.9.1] - 2026-01-28

### Added
- LLM note quality verification

## [0.9.0] - 2026-01-28

### Added
- First public release
- Homebrew tap installation
- Multi-architecture builds (Intel + Apple Silicon)

## [0.8.3] - 2026-01-28

### Added
- Database recovery tools
- Note re-indexing capability

## [0.8.2] - 2026-01-28

### Added
- Redesigned Settings with tabbed navigation
- Intuitive labels for settings

### Fixed
- API key validation
- Backfill issues

## [0.8.1] - 2026-01-27

### Added
- LLM tool calling for web search
- Rate limiting for API calls

### Fixed
- Backfill reliability

## [0.8.0] - 2026-01-27

### Added
- Web search integration with Perplexity-style citations
- Unified citation system for notes and web sources

## [0.7.2] - 2026-01-26

### Added
- Reset all data feature
- Memory included in data export

## [0.7.0] - 2026-01-25

### Added
- Knowledge graph visualization
- Entity extraction and relationship mapping
- Graph-expanded search

## [0.6.0] - 2026-01-20

### Added
- Daily revision pipeline
- Entity normalization across notes

## [0.5.0] - 2026-01-15

### Added
- Hourly summarization with LLM vision
- Keyframe selection algorithm
- Structured note generation

## [0.4.0] - 2026-01-10

### Added
- Chat interface with time filtering
- Citation support with note references

## [0.3.0] - 2026-01-05

### Added
- Screenshot capture daemon
- Foreground app detection
- Now playing detection (Spotify, Apple Music)

## [0.2.0] - 2025-12-20

### Added
- SQLite database with sqlite-vec for embeddings
- Basic note storage

## [0.1.0] - 2025-12-01

### Added
- Initial project structure
- Electron app shell
- Python backend foundation
