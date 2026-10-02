.PHONY: all help

HAS_DEBUG ?= 0
HAS_BATTERY ?= 0
MAX_KEYS ?= 500
# APPLE keeps the historical default. GOOGLE_FMDN and DUAL are the spec
# window, 2^10 seconds. A different interval walks off the EID table.
ifneq ($(filter GOOGLE_FMDN DUAL,$(FIND_NETWORK)),)
  ifeq ($(origin KEY_ROTATION_INTERVAL),command line)
    ifneq ($(KEY_ROTATION_INTERVAL),1024)
      $(error FIND_NETWORK=$(FIND_NETWORK) requires KEY_ROTATION_INTERVAL=1024 (K=10); got $(KEY_ROTATION_INTERVAL))
    endif
  endif
  KEY_ROTATION_INTERVAL := 1024
else
  KEY_ROTATION_INTERVAL ?= 3600
endif
ADVERTISING_INTERVAL ?= 1000
RANDOM_ROTATE_KEYS ?= 1
FIND_NETWORK ?= APPLE

GNU_INSTALL_ROOT ?= $(CURDIR)/nrf-sdk/gcc-arm-none-eabi-6-2017-q2-update


TARGETS := \
	nrf51822_xxac \
	nrf51822_xxac-dcdc \
	nrf52810_xxaa \
	nrf52810_xxaa-dcdc \
	nrf52832_xxaa \
	nrf52832_xxaa-dcdc \
	nrf52832_yj17024

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  all        - build all targets"
	@echo "  clean      - clean all targets"

# Define a recipe to build each target individually
define build_target
.PHONY: $(1)
DIR_$(1) := $(shell echo $(1) | cut -d'_' -f1)
GNU_INSTALL_ROOT_NO_SLASH := $(patsubst %/,%,$$(GNU_INSTALL_ROOT))
TOOLCHAIN_DIR := $(shell dirname $(GNU_INSTALL_ROOT_NO_SLASH))

$(1):
	$$(MAKE) -C $$(DIR_$(1))/armgcc \
		GNU_INSTALL_ROOT=$$(if $$(findstring nrf51,$$(DIR_$(1))),$$(GNU_INSTALL_ROOT)/,$$(GNU_INSTALL_ROOT)/bin/) \
		MAX_KEYS=$(MAX_KEYS) \
		HAS_DEBUG=$(HAS_DEBUG) \
		HAS_BATTERY=$(HAS_BATTERY) \
		KEY_ROTATION_INTERVAL=$(KEY_ROTATION_INTERVAL) \
		ADVERTISING_INTERVAL=$(ADVERTISING_INTERVAL) \
		RANDOM_ROTATE_KEYS=$(RANDOM_ROTATE_KEYS) \
		FIND_NETWORK=$(FIND_NETWORK) \
		$(1) bin_$(1)

	mkdir -p ./release
	cp $$(DIR_$(1))/armgcc/_build/*_s???.bin ./release/
	@echo "# Build options for $(1)" > ./release/$(1).txt
	@echo "GNU_INSTALL_ROOT=$$(shell basename $$(GNU_INSTALL_ROOT))" >> ./release/$(1).txt
	@echo "MAX_KEYS=$(MAX_KEYS)" >> ./release/$(1).txt
	@echo "HAS_DEBUG=$(HAS_DEBUG)" >> ./release/$(1).txt
	@echo "HAS_BATTERY=$(HAS_BATTERY)" >> ./release/$(1).txt
	@echo "KEY_ROTATION_INTERVAL=$(KEY_ROTATION_INTERVAL)" >> ./release/$(1).txt
	@echo "ADVERTISING_INTERVAL=$(ADVERTISING_INTERVAL)" >> ./release/$(1).txt
	@echo "RANDOM_ROTATE_KEYS=$(RANDOM_ROTATE_KEYS)" >> ./release/$(1).txt
	@echo "FIND_NETWORK=$(FIND_NETWORK)" >> ./release/$(1).txt


$(1)-clean:
	$$(MAKE) -C $$(DIR_$(1))/armgcc clean \
		GNU_INSTALL_ROOT=$$(if $$(findstring nrf51,$$(DIR_$(1))),$$(GNU_INSTALL_ROOT),$$(GNU_INSTALL_ROOT)/bin/)

endef

# Generate rules for each target in the TARGETS list
$(foreach target,$(TARGETS),$(eval $(call build_target,$(target))))

# Define all target to depend on all individual targets
all: $(TARGETS)

clean: $(foreach target,$(TARGETS),$(target)-clean)
	rm -rf ./release
