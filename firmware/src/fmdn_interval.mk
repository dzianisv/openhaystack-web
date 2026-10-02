# K=10 guard. Included before the nRF SDK so a bad FMDN interval fails
# even when nRF5_SDK is not downloaded. 0 means "unset" in the chip makefile.
ifneq ($(filter GOOGLE_FMDN DUAL,$(FIND_NETWORK)),)
  ifneq ($(KEY_ROTATION_INTERVAL),)
    ifneq ($(KEY_ROTATION_INTERVAL),0)
      ifneq ($(KEY_ROTATION_INTERVAL),1024)
        $(error FIND_NETWORK=$(FIND_NETWORK) requires KEY_ROTATION_INTERVAL=1024 (2^10 seconds); got $(KEY_ROTATION_INTERVAL))
      endif
    endif
  endif
endif
