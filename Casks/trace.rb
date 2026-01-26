# Homebrew Cask for Trace
# A second brain built from your digital activity

cask "trace" do
  version "0.5.5"

  on_arm do
    sha256 "205244df6075343efc30dd080a86cf5c9e81b84cbd67597c2538932cf660fcd3"
    url "file:///Users/junkim/Trace/electron/release/Trace-#{version}-arm64.dmg"
  end

  on_intel do
    sha256 "7a81cebc17db26004f7b1d1d54504b722b838f293e861a15da276554493ee331"
    url "file:///Users/junkim/Trace/electron/release/Trace-#{version}.dmg"
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
