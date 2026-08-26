using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Windows.Forms;

// 마계전기 디스가이아 2 PORTABLE (ULJS00183) 한국어화 — ISO 제자리 패처
//
// OGMD 패처(work_ogmd/iso_quickpatch)와 같은 구조지만 D2 는 훨씬 단순하다.
// 원본과 패치본 ISO 크기가 완전히 동일하므로(854,360,064B) ISO 내부 파일을 찾을
// 필요 없이 **절대 오프셋 구간**만 덮어쓰면 된다.
//
// 패치 데이터 D2_ISO_ranges.bin 포맷 (build_range_pack.py 생성).
// v20260829 부터 exe 에 임베드하지 않고 **같은 폴더의 별도 파일**로 배포한다
// (미서명 exe + 11MB 블롭이 Defender 오탐을 유발했다 — OpenPatchData 주석 참고):
//   magic "D2PSPRNG1" / u32 version / u16 titleLen + utf8 title
//   u64 isoSize / 32B srcHash / 32B dstHash / u32 rangeCount
//   rangeCount x { u64 offset, u32 length, length bytes }
internal static class D2IsoQuickPatch
{
    private const string VersionText = "v20260829";
    private const string PatchResourceName = "D2_ISO_ranges.bin";
    private const string PackMagic = "D2PSPRNG1";
    private const int FormatVersion = 1;
    private const int HashSize = 32;
    private const uint AttachParentProcess = 0xFFFFFFFF;

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool AttachConsole(uint processId);

    private sealed class PatchRange
    {
        public long Offset;
        public byte[] Data;
    }

    private sealed class Pack
    {
        public string Title;
        public long IsoSize;
        public byte[] SourceHash;
        public byte[] TargetHash;
        public List<PatchRange> Ranges;
        public long PayloadBytes;
    }

    private enum Mode { Patch, Restore, Verify }

    // ---------- 리소스 ----------

    // 패치 데이터를 **exe 밖의 별도 파일**에서 읽는다.
    //
    // ★ 예전에는 11MB 짜리 구간 데이터를 exe 안에 임베드했다. 그 결과 "17KB 코드 +
    //   11MB 불투명 블롭" 인 미서명 실행 파일이 되어, Windows Defender 의 클라우드
    //   ML 휴리스틱과 SmartScreen 이 이를 악성으로 오탐해 **다운로드 자체가 막히는**
    //   사용자가 나왔다(오탐 신고 2건). 데이터를 밖으로 빼면 exe 는 17KB 짜리
    //   평범한 크기가 되어 그 요인이 사라진다.
    //
    //   따라서 exe 와 D2_ISO_ranges.bin 은 **항상 같은 폴더에 함께 두어야 한다.**
    private static Stream OpenPatchData()
    {
        string exeDir = Path.GetDirectoryName(
            Assembly.GetExecutingAssembly().Location);
        string[] candidates = new string[]
        {
            string.IsNullOrEmpty(exeDir) ? PatchResourceName
                                         : Path.Combine(exeDir, PatchResourceName),
            Path.Combine(Directory.GetCurrentDirectory(), PatchResourceName),
        };
        foreach (string path in candidates)
        {
            if (File.Exists(path))
                return new FileStream(path, FileMode.Open, FileAccess.Read,
                                      FileShare.Read, 1 << 20);
        }

        // 구버전 호환: 임베드되어 있으면 그것도 받아들인다.
        Stream embedded = Assembly.GetExecutingAssembly()
            .GetManifestResourceStream(PatchResourceName);
        if (embedded != null)
            return embedded;

        throw new FileNotFoundException(
            "패치 데이터 파일을 찾을 수 없습니다: " + PatchResourceName + "\n\n" +
            "이 프로그램은 같은 폴더에 있는 " + PatchResourceName + " 을 읽습니다.\n" +
            "ZIP 을 풀 때 patcher 폴더의 두 파일(exe 와 .bin)을 함께 두세요.\n" +
            "exe 만 따로 옮기면 동작하지 않습니다.");
    }

    private static Pack LoadPack()
    {
        Stream resource = OpenPatchData();

        using (resource)
        using (BinaryReader r = new BinaryReader(resource, Encoding.UTF8))
        {
            byte[] magic = r.ReadBytes(PackMagic.Length);
            if (Encoding.ASCII.GetString(magic) != PackMagic)
                throw new InvalidDataException("패치 리소스 형식이 올바르지 않습니다.");
            int version = r.ReadInt32();
            if (version != FormatVersion)
                throw new InvalidDataException("지원하지 않는 패치 버전: " + version);

            int titleLen = r.ReadUInt16();
            string title = Encoding.UTF8.GetString(r.ReadBytes(titleLen));

            Pack pack = new Pack();
            pack.Title = title;
            pack.IsoSize = r.ReadInt64();
            pack.SourceHash = r.ReadBytes(HashSize);
            pack.TargetHash = r.ReadBytes(HashSize);

            int count = r.ReadInt32();
            pack.Ranges = new List<PatchRange>(count);
            long payload = 0;
            for (int i = 0; i < count; i++)
            {
                PatchRange range = new PatchRange();
                range.Offset = r.ReadInt64();
                int length = r.ReadInt32();
                range.Data = r.ReadBytes(length);
                if (range.Data.Length != length)
                    throw new InvalidDataException("패치 리소스가 손상되었습니다.");
                payload += length;
                pack.Ranges.Add(range);
            }
            pack.PayloadBytes = payload;
            if (resource.Position != resource.Length)
                throw new InvalidDataException("패치 리소스 뒤에 잉여 데이터가 있습니다.");
            return pack;
        }
    }

    // ---------- 해시 ----------

    private static string Sha256(string path, Action<long, long> progress)
    {
        long total = new FileInfo(path).Length;
        long done = 0;
        using (SHA256 sha = SHA256.Create())
        using (FileStream fs = new FileStream(path, FileMode.Open, FileAccess.Read,
                                              FileShare.Read, 1 << 20))
        {
            byte[] buffer = new byte[4 << 20];
            int read;
            while ((read = fs.Read(buffer, 0, buffer.Length)) > 0)
            {
                sha.TransformBlock(buffer, 0, read, null, 0);
                done += read;
                if (progress != null) progress(done, total);
            }
            sha.TransformFinalBlock(new byte[0], 0, 0);
            return BitConverter.ToString(sha.Hash).Replace("-", string.Empty);
        }
    }

    private static string Hex(byte[] data)
    {
        return BitConverter.ToString(data).Replace("-", string.Empty);
    }

    // ---------- 동작 ----------

    private static void Run(string isoPath, Mode mode, Action<string> log,
                            Action<int> progress)
    {
        Pack pack = LoadPack();
        log(pack.Title);
        log("패처 " + VersionText);
        log(string.Format(CultureInfo.InvariantCulture,
            "구간 {0:N0}개 / 페이로드 {1:N0}B", pack.Ranges.Count, pack.PayloadBytes));
        log(string.Empty);

        if (!File.Exists(isoPath))
            throw new FileNotFoundException("ISO 를 찾을 수 없습니다: " + isoPath);

        FileInfo info = new FileInfo(isoPath);
        if (info.IsReadOnly)
            throw new IOException("ISO 가 읽기 전용입니다. 속성에서 읽기 전용을 해제하세요.");
        if (info.Length != pack.IsoSize)
            throw new InvalidDataException(string.Format(CultureInfo.InvariantCulture,
                "ISO 크기가 다릅니다.\n필요: {0:N0}B\n현재: {1:N0}B\n" +
                "일본판 원본(Makai Senki Disgaea 2 Portable (Japan) (PSP) (PSN).iso)인지 확인하세요.",
                pack.IsoSize, info.Length));

        log("현재 ISO 해시 확인 중…");
        string current = Sha256(isoPath, delegate(long d, long t)
        {
            if (progress != null) progress((int)(d * 50 / Math.Max(1, t)));
        });
        string src = Hex(pack.SourceHash);
        string dst = Hex(pack.TargetHash);

        bool isOriginal = string.Equals(current, src, StringComparison.OrdinalIgnoreCase);
        bool isPatched = string.Equals(current, dst, StringComparison.OrdinalIgnoreCase);

        log("  " + current);
        if (isOriginal) log("  -> 원본(미패치) 상태입니다.");
        else if (isPatched) log("  -> 이미 한국어화가 적용된 상태입니다.");
        else log("  -> 원본도 패치본도 아닙니다.");
        log(string.Empty);

        if (mode == Mode.Verify)
        {
            if (isPatched) log("검증 결과: 한국어화 적용됨 (정상).");
            else if (isOriginal) log("검증 결과: 원본. 아직 적용되지 않았습니다.");
            else
            {
                log("검증 결과: 알 수 없는 ISO 입니다.");
                log("다른 패치가 적용되었거나 원본이 아닐 수 있습니다.");
            }
            if (progress != null) progress(100);
            return;
        }

        if (mode == Mode.Patch)
        {
            if (isPatched)
            {
                log("이미 적용되어 있어 할 일이 없습니다.");
                if (progress != null) progress(100);
                return;
            }
            if (!isOriginal)
                throw new InvalidDataException(
                    "원본 ISO 가 아닙니다.\n\n" +
                    "이 패처는 지정된 일본판 원본에만 적용됩니다.\n" +
                    "이미 다른 패치(xdelta 등)를 적용했다면 원본을 다시 준비하세요.");
        }
        else // Restore
        {
            if (isOriginal)
            {
                log("이미 원본 상태입니다.");
                if (progress != null) progress(100);
                return;
            }
            if (!isPatched)
                throw new InvalidDataException(
                    "이 패처로 적용한 ISO 가 아닙니다. 되돌릴 수 없습니다.");
        }

        // 리소스에는 패치본 구간만 들어 있으므로, 되돌리기는 패치 때 만든
        // .d2bak 백업이 있어야 한다 (RestoreFromBackup 이 담당).
        if (mode == Mode.Restore)
            throw new InvalidDataException(
                "되돌리기는 패치 시 생성된 백업 파일(.d2bak)이 필요합니다.\n" +
                "[백업으로 되돌리기] 를 사용하세요.");

        string backupPath = isoPath + ".d2bak";
        log("백업 생성: " + Path.GetFileName(backupPath));
        using (FileStream iso = new FileStream(isoPath, FileMode.Open, FileAccess.Read,
                                              FileShare.Read, 1 << 20))
        using (FileStream bak = new FileStream(backupPath, FileMode.Create,
                                              FileAccess.Write, FileShare.None, 1 << 20))
        using (BinaryWriter w = new BinaryWriter(bak))
        {
            w.Write(Encoding.ASCII.GetBytes("D2PSPBAK1"));
            w.Write(FormatVersion);
            w.Write(pack.IsoSize);
            w.Write(pack.SourceHash);
            w.Write(pack.Ranges.Count);
            byte[] buffer = new byte[1 << 20];
            for (int i = 0; i < pack.Ranges.Count; i++)
            {
                PatchRange range = pack.Ranges[i];
                iso.Seek(range.Offset, SeekOrigin.Begin);
                if (buffer.Length < range.Data.Length) buffer = new byte[range.Data.Length];
                int read = 0;
                while (read < range.Data.Length)
                {
                    int n = iso.Read(buffer, read, range.Data.Length - read);
                    if (n <= 0) throw new IOException("ISO 읽기 실패");
                    read += n;
                }
                w.Write(range.Offset);
                w.Write(range.Data.Length);
                w.Write(buffer, 0, range.Data.Length);
                if (progress != null) progress(50 + (int)(i * 20L / pack.Ranges.Count));
            }
        }

        log("구간 적용 중…");
        using (FileStream iso = new FileStream(isoPath, FileMode.Open, FileAccess.ReadWrite,
                                              FileShare.None, 1 << 20))
        {
            for (int i = 0; i < pack.Ranges.Count; i++)
            {
                PatchRange range = pack.Ranges[i];
                iso.Seek(range.Offset, SeekOrigin.Begin);
                iso.Write(range.Data, 0, range.Data.Length);
                if (progress != null) progress(70 + (int)(i * 15L / pack.Ranges.Count));
            }
            iso.Flush(true);
        }

        log("적용 후 해시 확인 중…");
        string after = Sha256(isoPath, delegate(long d, long t)
        {
            if (progress != null) progress(85 + (int)(d * 15 / Math.Max(1, t)));
        });
        log("  " + after);
        if (!string.Equals(after, dst, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException(
                "적용 후 해시가 기대값과 다릅니다.\n백업(.d2bak)으로 되돌리세요.");

        log(string.Empty);
        log("완료. 한국어화가 적용되었습니다.");
        log("PPSSPP 로 실행하세요. 실기(CFW)에서는 동작하지 않습니다.");
        if (progress != null) progress(100);
    }

    private static void RestoreFromBackup(string isoPath, string backupPath,
                                          Action<string> log, Action<int> progress)
    {
        Pack pack = LoadPack();
        log("백업으로 되돌리기");
        using (FileStream bak = new FileStream(backupPath, FileMode.Open, FileAccess.Read,
                                              FileShare.Read, 1 << 20))
        using (BinaryReader r = new BinaryReader(bak))
        {
            string magic = Encoding.ASCII.GetString(r.ReadBytes(9));
            if (magic != "D2PSPBAK1")
                throw new InvalidDataException("백업 파일 형식이 올바르지 않습니다.");
            r.ReadInt32();
            long isoSize = r.ReadInt64();
            r.ReadBytes(HashSize);
            int count = r.ReadInt32();

            FileInfo info = new FileInfo(isoPath);
            if (info.Length != isoSize)
                throw new InvalidDataException("ISO 크기가 백업과 다릅니다.");

            using (FileStream iso = new FileStream(isoPath, FileMode.Open,
                                                  FileAccess.ReadWrite, FileShare.None, 1 << 20))
            {
                for (int i = 0; i < count; i++)
                {
                    long off = r.ReadInt64();
                    int len = r.ReadInt32();
                    byte[] data = r.ReadBytes(len);
                    iso.Seek(off, SeekOrigin.Begin);
                    iso.Write(data, 0, len);
                    if (progress != null) progress((int)(i * 90L / count));
                }
                iso.Flush(true);
            }
        }
        log("해시 확인 중…");
        string after = Sha256(isoPath, null);
        log("  " + after);
        if (string.Equals(after, Hex(pack.SourceHash), StringComparison.OrdinalIgnoreCase))
            log("완료. 원본 상태로 되돌렸습니다.");
        else
            log("경고: 원본 해시와 다릅니다. ISO 를 다시 준비하는 것이 안전합니다.");
        if (progress != null) progress(100);
    }

    // ---------- GUI ----------

    private sealed class MainForm : Form
    {
        private readonly TextBox isoBox = new TextBox();
        private readonly TextBox logBox = new TextBox();
        private readonly ProgressBar bar = new ProgressBar();
        private readonly Button patchBtn = new Button();
        private readonly Button verifyBtn = new Button();
        private readonly Button restoreBtn = new Button();

        public MainForm(string initialIso)
        {
            Text = "디스가이아 2 PORTABLE 한국어화 패처 " + VersionText;
            Width = 760;
            Height = 520;
            StartPosition = FormStartPosition.CenterScreen;
            Font = new Font("맑은 고딕", 9F);
            AllowDrop = true;
            DragEnter += delegate(object s, DragEventArgs e)
            {
                e.Effect = e.Data.GetDataPresent(DataFormats.FileDrop)
                    ? DragDropEffects.Copy : DragDropEffects.None;
            };
            DragDrop += delegate(object s, DragEventArgs e)
            {
                string[] files = (string[])e.Data.GetData(DataFormats.FileDrop);
                if (files.Length > 0) isoBox.Text = files[0];
            };

            Label lbl = new Label();
            lbl.Text = "ISO 경로 (드래그 앤 드롭 가능)";
            lbl.SetBounds(12, 12, 300, 18);
            Controls.Add(lbl);

            isoBox.SetBounds(12, 32, 620, 24);
            isoBox.Text = initialIso ?? string.Empty;
            Controls.Add(isoBox);

            Button browse = new Button();
            browse.Text = "찾기";
            browse.SetBounds(640, 31, 90, 26);
            browse.Click += delegate
            {
                using (OpenFileDialog dlg = new OpenFileDialog())
                {
                    dlg.Filter = "PSP ISO (*.iso)|*.iso|모든 파일 (*.*)|*.*";
                    if (dlg.ShowDialog(this) == DialogResult.OK) isoBox.Text = dlg.FileName;
                }
            };
            Controls.Add(browse);

            patchBtn.Text = "한국어화 적용";
            patchBtn.SetBounds(12, 68, 150, 34);
            patchBtn.Click += delegate { Start(Mode.Patch); };
            Controls.Add(patchBtn);

            verifyBtn.Text = "상태 확인";
            verifyBtn.SetBounds(172, 68, 120, 34);
            verifyBtn.Click += delegate { Start(Mode.Verify); };
            Controls.Add(verifyBtn);

            restoreBtn.Text = "백업으로 되돌리기";
            restoreBtn.SetBounds(302, 68, 160, 34);
            restoreBtn.Click += delegate { StartRestore(); };
            Controls.Add(restoreBtn);

            bar.SetBounds(12, 112, 718, 18);
            Controls.Add(bar);

            logBox.SetBounds(12, 140, 718, 330);
            logBox.Multiline = true;
            logBox.ReadOnly = true;
            logBox.ScrollBars = ScrollBars.Vertical;
            logBox.Font = new Font("Consolas", 9F);
            Controls.Add(logBox);

            Log("일본판 원본 ISO 를 선택하고 [한국어화 적용]을 누르세요.");
            Log("원본: Makai Senki Disgaea 2 Portable (Japan) (PSP) (PSN).iso");
            Log("적용 전 원본 구간을 .d2bak 백업으로 남깁니다.");
            Log(string.Empty);
            Log("※ PPSSPP 전용입니다. 실기(CFW)에서는 동작하지 않습니다.");
        }

        private void Log(string text)
        {
            if (InvokeRequired) { BeginInvoke((Action<string>)Log, text); return; }
            logBox.AppendText(text + Environment.NewLine);
        }

        private void SetProgress(int value)
        {
            if (InvokeRequired) { BeginInvoke((Action<int>)SetProgress, value); return; }
            bar.Value = Math.Max(0, Math.Min(100, value));
        }

        private void SetBusy(bool busy)
        {
            if (InvokeRequired) { BeginInvoke((Action<bool>)SetBusy, busy); return; }
            patchBtn.Enabled = verifyBtn.Enabled = restoreBtn.Enabled = !busy;
        }

        private void Start(Mode mode)
        {
            string iso = isoBox.Text.Trim().Trim('"');
            if (iso.Length == 0) { MessageBox.Show(this, "ISO 를 선택하세요."); return; }
            SetBusy(true);
            SetProgress(0);
            logBox.Clear();
            Thread t = new Thread(delegate()
            {
                try { Run(iso, mode, Log, SetProgress); }
                catch (Exception ex) { Log(string.Empty); Log("오류: " + ex.Message); }
                finally { SetBusy(false); }
            });
            t.IsBackground = true;
            t.Start();
        }

        private void StartRestore()
        {
            string iso = isoBox.Text.Trim().Trim('"');
            if (iso.Length == 0) { MessageBox.Show(this, "ISO 를 선택하세요."); return; }
            string backup = iso + ".d2bak";
            if (!File.Exists(backup))
            {
                using (OpenFileDialog dlg = new OpenFileDialog())
                {
                    dlg.Filter = "백업 (*.d2bak)|*.d2bak|모든 파일 (*.*)|*.*";
                    if (dlg.ShowDialog(this) != DialogResult.OK) return;
                    backup = dlg.FileName;
                }
            }
            SetBusy(true);
            SetProgress(0);
            logBox.Clear();
            string bk = backup;
            Thread t = new Thread(delegate()
            {
                try { RestoreFromBackup(iso, bk, Log, SetProgress); }
                catch (Exception ex) { Log(string.Empty); Log("오류: " + ex.Message); }
                finally { SetBusy(false); }
            });
            t.IsBackground = true;
            t.Start();
        }
    }

    // ---------- 진입점 ----------

    [STAThread]
    private static int Main(string[] args)
    {
        bool cli = false;
        string iso = null;
        Mode mode = Mode.Patch;
        for (int i = 0; i < args.Length; i++)
        {
            string a = args[i];
            if (a == "--cli") cli = true;
            else if (a == "--verify") { cli = true; mode = Mode.Verify; }
            else if (iso == null) iso = a;
        }

        if (!cli)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm(iso));
            return 0;
        }

        AttachConsole(AttachParentProcess);
        try
        {
            if (iso == null) { Console.WriteLine("사용: D2_ISO_QuickPatch.exe <ISO> [--verify]"); return 2; }
            Run(iso, mode, Console.WriteLine, null);
            return 0;
        }
        catch (Exception ex)
        {
            Console.WriteLine("오류: " + ex.Message);
            return 1;
        }
    }
}
