# Homebrew Cask for Trace
# A second brain built from your digital activity

cask "trace" do
  version "0.2.3"

  on_arm do
    sha256 "fa6be1ba833a35042a8b721aa8e8fae091e4de6b972609fe9435813a2ece4d11"
    url "https://github.com/junkim100/Trace/releases/download/v#{version}/Trace-#{version}-arm64.dmg"
  end

  on_intel do
    sha256 "2cb5b7b0ad968a30beaa466b51396f7b3c96b859e37a9c79da5a7940955d46c0"
    url "https://github.com/junkim100/Trace/releases/download/v#{version}/Trace-#{version}.dmg"
  end

  name "Trace"
  desc "A second brain built from your digital activity"
  homepage "https://github.com/junkim100/Trace"

  livecheck do
    url :url
    strategy :github_latest
  end

  app "Trace.app"

  postflight do
    # Remove quarantine attribute to avoid "damaged" error
    system_command "/usr/bin/xattr",
                   args: ["-cr", "#{appdir}/Trace.app"],
                   sudo: false
  end

  zap trash: [
    "~/Library/Application Support/Trace",
    "~/Library/Preferences/com.trace.app.plist",
    "~/Library/Caches/com.trace.app",
  ]

  caveats <<~EOS
    Trace requires the following permissions:
    - Screen Recording (required)
    - Accessibility (required)
    - Location Services (optional, requires signed app)

    On first launch:
    1. Open Trace from Applications
    2. Grant permissions when prompted in System Settings
    3. Set your OpenAI API key in Settings (Cmd+,)
  EOS
end
