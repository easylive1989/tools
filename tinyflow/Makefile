APP_NAME = TinyFlow
BUILD_DIR = .build/debug
APP_BUNDLE = $(APP_NAME).app
CONTENTS = $(APP_BUNDLE)/Contents
MACOS_DIR = $(CONTENTS)/MacOS

.PHONY: build app run clean

build:
	swift build

app: build
	@rm -rf $(APP_BUNDLE)
	@mkdir -p $(MACOS_DIR)
	@cp $(BUILD_DIR)/$(APP_NAME) $(MACOS_DIR)/$(APP_NAME)
	@cp Info.plist $(CONTENTS)/Info.plist
	@echo "✅ $(APP_BUNDLE) 已建立"

run: app
	@open $(APP_BUNDLE)

clean:
	@rm -rf $(APP_BUNDLE) .build
