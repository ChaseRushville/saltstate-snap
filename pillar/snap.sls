snap:
  apply: True

  snaps_purged:
    # the order of snaps here matters

    firefox: True
    snap-store: True
    bare: True
    core22: True
    snapd: True

  aptpref_file: /etc/apt/preferences.d/nosnap.pref
