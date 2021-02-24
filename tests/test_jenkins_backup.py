from dcos_migrate.plugins.marathon import MarathonPlugin
from dcos_migrate.plugins.jenkins import JenkinsPlugin
from dcos_migrate.system import DCOSClient, BackupList
import json


def test_jenkins_backup():
    with open('tests/examples/jenkins.json') as json_file:
        data = json.load(json_file)
        bl = BackupList()
        m = MarathonPlugin()
        backup = m.createBackup(data)
        bl.append(backup)

        j = JenkinsPlugin()
        jbl = j.backup(client=DCOSClient(), backupList=bl)

        assert len(jbl) == 1

        assert jbl[0].data['version'] == "3.6.1-2.190.1"
        assert jbl[0].data['options']['service']['mem'] == 4096
        assert jbl[0].data['options']['service']['cpus'] == 1
