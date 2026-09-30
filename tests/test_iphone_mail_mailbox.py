import email.message
import pytest
from pathlib import Path
from planning_bot.tools import iphone_mail_sync as mail


@pytest.fixture(autouse=True)
def isolated_mail_policy(monkeypatch):
    from shared import yaml_config
    load = yaml_config.load_merged_config
    def config(directory, name):
        result = load(directory, name)
        return dict(result, mail={"archive_successful": False}) if name == "health_backfill" else result
    monkeypatch.setattr(yaml_config, "load_merged_config", config)


class FakeIMAP:
    def __init__(self, *args):
        self.calls=[]
    def login(self,*args): pass
    def select(self,mailbox,readonly=False):
        self.calls.append(("select",mailbox,readonly)); return "OK",[b"1"]
    def search(self,*args):
        self.calls.append(("search",args)); return "OK",[b"1"]
    def fetch(self,eid,query):
        self.calls.append(("fetch",query))
        msg=email.message.EmailMessage()
        msg['Subject']='MetricsTest'
        msg['Date']='Sun, 13 Sep 2026 10:00:00 +0000'
        msg['Message-ID']='<synthetic-test>'
        msg.set_content('ts: 13.09.2026, 10:00\nsteps: 1234\n')
        return "OK",[(b'1',msg.as_bytes())]
    def close(self): pass
    def logout(self): pass


def test_label_is_readonly_and_body_does_not_mark_read(tmp_path,monkeypatch):
    fake=FakeIMAP()
    monkeypatch.setattr(mail.imaplib,'IMAP4_SSL',lambda *a:fake)
    monkeypatch.setenv('GMAIL_IMAP_MAILBOX','ObsidianMetrics')
    monkeypatch.setenv('GMAIL_IMAP_SUBJECT','MetricsTest')
    result=mail.run_iphone_mail_sync(user='synthetic',app_password='synthetic',iphone_dir=tmp_path,
                                   today_only=False,since_days=3650)
    assert result['written']==1
    assert next(c for c in fake.calls if c[0]=='search')[1][1]=='SINCE'
    assert next(c for c in fake.calls if c[0]=='search')[1][3]=='SUBJECT'
    assert ('select','"ObsidianMetrics"',True) in fake.calls
    assert ('fetch','(BODY.PEEK[])') in fake.calls


def test_missing_label_does_not_silently_fall_back(tmp_path,monkeypatch):
    fake=FakeIMAP()
    fake.select=lambda *a,**k:('NO',[])
    monkeypatch.setattr(mail.imaplib,'IMAP4_SSL',lambda *a:fake)
    result=mail.run_iphone_mail_sync(user='synthetic',app_password='synthetic',iphone_dir=tmp_path)
    assert result['ok'] is False
    assert not list(tmp_path.glob('*.txt'))


def test_cyrillic_subject_uses_utf8_literal(tmp_path, monkeypatch):
    fake = FakeIMAP()
    subject = 'Метрики iPhone'
    def search(*args):
        # Reproduce imaplib's ASCII encoding of ordinary string arguments.
        for arg in args:
            if isinstance(arg, str):
                arg.encode('ascii')
        assert args[0] == 'UTF-8'
        assert args[-1] == 'SUBJECT'
        assert fake.literal == subject.encode('utf-8')
        return 'OK', [b'']
    fake.search = search
    monkeypatch.setattr(mail.imaplib, 'IMAP4_SSL', lambda *a: fake)
    monkeypatch.setenv('GMAIL_IMAP_SUBJECT', subject)
    result = mail.run_iphone_mail_sync(user='synthetic', app_password='synthetic',
                                      iphone_dir=tmp_path, today_only=False)
    assert result['ok'] and result['fetched'] == 0


def test_malformed_message_is_quarantined_in_state_and_not_retried(tmp_path, monkeypatch):
    fake = FakeIMAP()

    def empty_fetch(eid, query):
        fake.calls.append(("fetch", query))
        msg = email.message.EmailMessage()
        msg['Subject'] = 'MetricsTest'
        msg['Date'] = 'Sun, 13 Sep 2026 10:00:00 +0000'
        msg['Message-ID'] = '<empty-metrics-test>'
        msg.set_content('')
        return "OK", [(b'1', msg.as_bytes())]

    fake.fetch = empty_fetch
    monkeypatch.setattr(mail.imaplib, 'IMAP4_SSL', lambda *a: fake)
    monkeypatch.setenv('GMAIL_IMAP_SUBJECT', 'MetricsTest')

    first = mail.run_iphone_mail_sync(
        user='synthetic', app_password='synthetic', iphone_dir=tmp_path,
        today_only=False, since_days=3650,
    )
    assert first['rejected'] == 1
    state = mail._load_state(tmp_path / '.sync_state.json')
    assert '<empty-metrics-test>' in state['processed_ids']

    second = mail.run_iphone_mail_sync(
        user='synthetic', app_password='synthetic', iphone_dir=tmp_path,
        today_only=False, since_days=3650,
    )
    assert second['fetched'] == 0
    assert second['skipped'] == 1


def test_archive_only_after_valid_snapshot_is_written(tmp_path, monkeypatch):
    from shared import yaml_config
    fake=FakeIMAP();original=fake.fetch;archived=[]
    def fetch(eid,query):
        status,data=original(eid,query)
        return status,[(b'1 (UID 991 BODY[] {})',data[0][1])]
    fake.fetch=fetch
    def uid(*args):
        assert list(tmp_path.glob('*.txt')), 'Do not archive before writing the snapshot'
        archived.append(args);return 'OK',[]
    fake.uid=uid
    monkeypatch.setattr(mail.imaplib,'IMAP4_SSL',lambda *a:fake)
    real_load=yaml_config.load_merged_config
    monkeypatch.setattr(yaml_config,'load_merged_config',lambda directory,name: dict(real_load(directory,name),mail={'archive_successful':True}) if name=='health_backfill' else real_load(directory,name))
    monkeypatch.setenv('GMAIL_IMAP_SUBJECT','MetricsTest')
    monkeypatch.setenv('GMAIL_IMAP_MAILBOX','INBOX')
    monkeypatch.setenv('GMAIL_IMAP_HOST','imap.gmail.com')
    result=mail.run_iphone_mail_sync(user='synthetic',app_password='synthetic',iphone_dir=tmp_path,today_only=False,since_days=3650)
    assert result['written']==1 and result['archived']==1
    assert archived==[('STORE',b'991','-X-GM-LABELS',r'(\Inbox)')]
