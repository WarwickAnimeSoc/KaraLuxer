# -*- mode: python ; coding: utf-8 -*-


block_cipher = None


a = Analysis(['karaluxer.py'],
             pathex=[],
             binaries=[('C:/hostedtoolcache/windows/ffmpeg/5.0.1/x64/ffmpeg.exe', '.')],
             datas=[('C:/hostedtoolcache/windows/Python/3.10.8/x64/lib/site-packages/certifi/cacert.pem', 'certifi')],
             hiddenimports=[],
             hookspath=[],
             hooksconfig={},
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='karaluxer',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=True,
          disable_windowed_traceback=False,
          target_arch=None,
          codesign_identity=None,
          entitlements_file=None )
