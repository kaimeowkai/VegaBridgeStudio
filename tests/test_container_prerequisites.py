from vegabridge.android_runtime_probe import COMMAND, parse_observations, summarize


def test_enabled_kernel_options_never_imply_container_permission_or_apk_support():
    observation=parse_observations('MACHINE=x86_64\nKERNEL_USER_NS=y\nKERNEL_BINDERFS=y\nKERNEL_MEMFD=y\nMAX_USER_NAMESPACES=100\nNODE=/dev/binder:read-write-permissions','Developer shell')
    report=summarize([observation])
    assert report['containerReady'] is False and report['namespaceSyscallsTested'] is False
    assert report['kernelConfigurationIsNotPermissionProof'] is True
    assert report['apkExecutionTested'] is False


def test_disabled_binderfs_is_a_scoped_conventional_container_blocker():
    observation=parse_observations('MACHINE=x86_64\nKERNEL_BINDERFS=n\nNODE=/dev/binder:read-write-permissions','Developer component shell')
    report=summarize([observation])
    assert any('Developer component shell' in note and 'private-Binder' in note for note in report['unresolvedPrerequisites'])
    assert report['allAndroidAppsSupported'] is False


def test_unavailable_kernel_configuration_stays_unknown_and_zero_namespace_limit_is_reported():
    observation=parse_observations('MACHINE=armv7l\nMAX_USER_NAMESPACES=0\nNO_NEW_PRIVS=1\nSECCOMP=2','Developer shell')
    report=summarize([observation])
    assert 'KERNEL_BINDERFS' not in observation['values']
    assert not any('disables binderfs' in note for note in report['unresolvedPrerequisites'])
    assert any('user namespaces are disabled' in note for note in report['unresolvedPrerequisites'])
    assert '\n' not in COMMAND and 'mount ' not in COMMAND and 'unshare ' not in COMMAND
