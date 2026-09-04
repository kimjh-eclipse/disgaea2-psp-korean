using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Windows.Forms;

// 마계전기 디스가이아 2 PORTABLE (ULJS00183) 한국어화 — ISO + DLC 통합 패처
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
    private const string VersionText = "v20260904";
    private const string PatchResourceName = "D2_ISO_ranges.bin";
    private const string SaveMapName = "D2_SAVE_codemap.bin";
    private const string SaveMapMagic = "D2SAVMAP1";
    private const string AssemblyMapName = "D2_SAVE_assemblymap.bin";
    private const string AssemblyMapMagic = "D2ASMMAP1";
    private const string SaveCryptoName = "D2_SAVE_crypto.exe";
    private const string SaveCryptoKey = "DISGAEA120060528";
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

    private sealed class DlcGroup
    {
        public int First, Last;
        public string Representative, SourceHash, TargetHash;
        public DlcGroup(int first, int last, string representative,
                        string sourceHash, string targetHash)
        {
            First = first; Last = last; Representative = representative;
            SourceHash = sourceHash; TargetHash = targetHash;
        }
    }

    private static readonly DlcGroup[] DlcGroups = new DlcGroup[]
    {
        new DlcGroup(0, 4, "00",
            "FE96431E2881A3A3166163BE46FC3977A78731814E441D775E07D7C2F7ED3AED",
            "159B14C15561D860E4CE01B281D7E32738D1A3F1C3535D28F2C25AE56C160387"),
        new DlcGroup(5, 8, "05",
            "3A43D79E4CC5D2DB32F1282EB7C072A39BFD2F8C603B1F8B3A1FA7CD23B26C3D",
            "A354481FC554E3A748A1668093EE62BCEA0DFB2B159C81F0BD6FD070A6CA82E9"),
        new DlcGroup(9, 12, "09",
            "605ABE5F19D02744EF2F17582E2E9009CC490AFA513CB0BB9379DE643E205FB8",
            "9FB1D9D8926FF3404C8B5C6C8BA9F74AA47C48D6160133DF242EA7D919D37684"),
        new DlcGroup(13, 16, "13",
            "C93C1B70F8615AFCCF51E83EA17D99BA4C9A2952986F75D21AAE1B22E181E52F",
            "A8AE280F8E0E18159E9DDD904A0AA583E67723E82C8FEBCCF9BD59AFAC1779F4"),
        new DlcGroup(17, 17, "17",
            "C0FC7185C43FC1D7D307E4AFE2F1B518AE95A2F4B5E21CD458B5950C6EC232B0",
            "230090E5558C051AE920A4A5D050F0BA2F2FBE28C02B13E1E2DD1992C3312A54"),
    };

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
        log("PPSSPP 로 실행하세요. 실기(CFW)는 아직 검증되지 않았습니다.");
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

    // ---------- DLC (PSP/GAME/ULJS00183) ----------

    private static string SidecarPath(string name)
    {
        string exeDir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        string first = string.IsNullOrEmpty(exeDir) ? name : Path.Combine(exeDir, name);
        if (File.Exists(first)) return first;
        string second = Path.Combine(Directory.GetCurrentDirectory(), name);
        if (File.Exists(second)) return second;
        throw new FileNotFoundException("패처 구성 파일을 찾을 수 없습니다: " + name);
    }

    private static string Q(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }

    private static void ApplyXdelta(string source, string patch, string output)
    {
        ProcessStartInfo info = new ProcessStartInfo();
        info.FileName = SidecarPath("xdelta.exe");
        info.Arguments = "-f -d -s " + Q(source) + " " + Q(patch) + " " + Q(output);
        info.UseShellExecute = false;
        info.CreateNoWindow = true;
        info.RedirectStandardOutput = true;
        info.RedirectStandardError = true;
        using (Process process = Process.Start(info))
        {
            string stdout = process.StandardOutput.ReadToEnd();
            string stderr = process.StandardError.ReadToEnd();
            process.WaitForExit();
            if (process.ExitCode != 0)
                throw new InvalidDataException(
                    "xdelta 적용 실패(" + process.ExitCode + ")\n" + stdout + stderr);
        }
    }

    private static void RunDlc(string dlcPath, Mode mode, Action<string> log,
                               Action<int> progress)
    {
        if (string.IsNullOrWhiteSpace(dlcPath))
        {
            log("DLC 폴더 미지정: DLC 패치는 건너뜁니다.");
            if (progress != null) progress(100);
            return;
        }
        dlcPath = dlcPath.Trim().Trim('"');
        if (!Directory.Exists(dlcPath))
            throw new DirectoryNotFoundException("DLC 폴더를 찾을 수 없습니다: " + dlcPath);

        log(string.Empty);
        log("DLC 확인: " + dlcPath);
        int present = 0, missing = 0, patched = 0, already = 0, mismatch = 0, restored = 0;
        int ordinal = 0;
        const int total = 18;

        foreach (DlcGroup group in DlcGroups)
        {
            string patchPath = null;
            for (int number = group.First; number <= group.Last; number++)
            {
                ordinal++;
                string name = "DL_JP_" + number.ToString("00", CultureInfo.InvariantCulture) + ".EDAT";
                string path = Path.Combine(dlcPath, name);
                string backup = path + ".d2bak";

                if (mode == Mode.Restore)
                {
                    if (!File.Exists(backup))
                    {
                        missing++;
                        log("  없음/백업 없음, 건너뜀: " + name);
                    }
                    else
                    {
                        string backupHash = Sha256(backup, null);
                        if (!string.Equals(backupHash, group.SourceHash,
                                           StringComparison.OrdinalIgnoreCase))
                        {
                            mismatch++;
                            log("  백업 해시 불일치, 건너뜀: " + name);
                        }
                        else
                        {
                            File.Copy(backup, path, true);
                            restored++;
                            log("  원본 복원: " + name);
                        }
                    }
                    if (progress != null) progress((int)(ordinal * 100L / total));
                    continue;
                }

                if (!File.Exists(path))
                {
                    missing++;
                    log("  없음, 건너뜀: " + name);
                    if (progress != null) progress((int)(ordinal * 100L / total));
                    continue;
                }
                present++;
                string current = Sha256(path, null);
                if (string.Equals(current, group.TargetHash, StringComparison.OrdinalIgnoreCase))
                {
                    already++;
                    log("  이미 적용됨: " + name);
                }
                else if (!string.Equals(current, group.SourceHash, StringComparison.OrdinalIgnoreCase))
                {
                    mismatch++;
                    log("  원본 해시 불일치, 건너뜀: " + name);
                }
                else if (mode == Mode.Verify)
                {
                    log("  원본(미패치): " + name);
                }
                else
                {
                    if (patchPath == null)
                        patchPath = SidecarPath(
                            "D2_DLC_group_" + group.Representative + ".xdelta");
                    if (!File.Exists(backup)) File.Copy(path, backup, false);
                    string temp = path + ".d2tmp";
                    if (File.Exists(temp)) File.Delete(temp);
                    try
                    {
                        ApplyXdelta(path, patchPath, temp);
                        string after = Sha256(temp, null);
                        if (!string.Equals(after, group.TargetHash,
                                           StringComparison.OrdinalIgnoreCase))
                            throw new InvalidDataException("DLC 적용 후 해시 불일치: " + name);
                        File.Replace(temp, path, null);
                        patched++;
                        log("  적용 완료: " + name);
                    }
                    finally
                    {
                        if (File.Exists(temp)) File.Delete(temp);
                    }
                }
                if (progress != null) progress((int)(ordinal * 100L / total));
            }
        }

        log(string.Format(CultureInfo.InvariantCulture,
            "DLC 결과: 존재 {0} / 적용 {1} / 이미 적용 {2} / 복원 {3} / 없음 {4} / 불일치 {5}",
            present, patched, already, restored, missing, mismatch));
        if (mismatch > 0)
            log("※ 해시 불일치 파일은 안전을 위해 수정하지 않았습니다.");
        if (progress != null) progress(100);
    }

    // ---------- GUI ----------

    private sealed class MainForm : Form
    {
        private readonly TextBox isoBox = new TextBox();
        private readonly TextBox dlcBox = new TextBox();
        private readonly TextBox logBox = new TextBox();
        private readonly ProgressBar bar = new ProgressBar();
        private readonly Button patchBtn = new Button();
        private readonly Button verifyBtn = new Button();
        private readonly Button restoreBtn = new Button();
        private readonly TextBox saveBox = new TextBox();
        private readonly Button saveCheckBtn = new Button();
        private readonly Button saveFixBtn = new Button();
        private readonly Button saveAssemblyBtn = new Button();

        public MainForm(string initialIso)
        {
            Text = "디스가이아 2 PORTABLE 한국어화 패처 " + VersionText;
            Width = 760;
            Height = 735;
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
                if (files.Length > 0)
                {
                    if (Directory.Exists(files[0])) dlcBox.Text = files[0];
                    else if (Path.GetFileName(files[0]).Equals(
                                 "DATA.BIN", StringComparison.OrdinalIgnoreCase))
                        saveBox.Text = files[0];
                    else isoBox.Text = files[0];
                }
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

            Label dlcLabel = new Label();
            dlcLabel.Text = "DLC 폴더 (선택 사항, PSP/GAME/ULJS00183)";
            dlcLabel.SetBounds(12, 68, 430, 18);
            Controls.Add(dlcLabel);

            dlcBox.SetBounds(12, 88, 620, 24);
            Controls.Add(dlcBox);

            Button dlcBrowse = new Button();
            dlcBrowse.Text = "찾기";
            dlcBrowse.SetBounds(640, 87, 90, 26);
            dlcBrowse.Click += delegate
            {
                using (FolderBrowserDialog dlg = new FolderBrowserDialog())
                {
                    dlg.Description = "PARAM.PBP와 DL_JP_*.EDAT가 있는 ULJS00183 폴더를 선택하세요.";
                    if (dlg.ShowDialog(this) == DialogResult.OK) dlcBox.Text = dlg.SelectedPath;
                }
            };
            Controls.Add(dlcBrowse);

            patchBtn.Text = "한국어화 적용";
            patchBtn.SetBounds(12, 124, 150, 34);
            patchBtn.Click += delegate { Start(Mode.Patch); };
            Controls.Add(patchBtn);

            verifyBtn.Text = "상태 확인";
            verifyBtn.SetBounds(172, 124, 120, 34);
            verifyBtn.Click += delegate { Start(Mode.Verify); };
            Controls.Add(verifyBtn);

            restoreBtn.Text = "백업으로 되돌리기";
            restoreBtn.SetBounds(302, 124, 160, 34);
            restoreBtn.Click += delegate { StartRestore(); };
            Controls.Add(restoreBtn);

            // ---- 세이브 글자 복구 ----
            //
            // v20260830 에서 얻은 아이템은 이름이 세이브에 그 시점 코드로 박혀 있어
            // 코드표를 되돌린 뒤 깨져 보인다. ISO 는 정상이므로 세이브만 고치면 된다.
            GroupBox saveGroup = new GroupBox();
            saveGroup.Text = "기존 세이브 보정";
            saveGroup.SetBounds(12, 168, 718, 164);
            Controls.Add(saveGroup);

            Label saveHint = new Label();
            // ★ 제약을 안내문에 명시한다. 평문 세이브만 고칠 수 있고, 대부분의
            //   사용자 세이브는 암호화 상태라 사전 작업이 반드시 필요하다.
            saveHint.Text = "평문 세이브만 고칠 수 있습니다. 암호화된 세이브는 진행되지 않습니다." + "\r\n"
                          + "PPSSPP 설정에서 저장 데이터 암호화를 끄고 새 슬롯에 저장한 뒤,"
                          + " 그 DATA.BIN 을 지정하세요.";
            saveHint.SetBounds(12, 18, 700, 36);
            saveGroup.Controls.Add(saveHint);

            saveBox.SetBounds(12, 60, 580, 24);
            saveGroup.Controls.Add(saveBox);

            Button saveBrowse = new Button();
            saveBrowse.Text = "찾기";
            saveBrowse.SetBounds(600, 59, 100, 26);
            saveBrowse.Click += delegate
            {
                using (OpenFileDialog dlg = new OpenFileDialog())
                {
                    dlg.Title = "평문 DATA.BIN 선택";
                    dlg.Filter = "PSP 세이브 (DATA.BIN)|DATA.BIN|모든 파일 (*.*)|*.*";
                    if (dlg.ShowDialog(this) == DialogResult.OK) saveBox.Text = dlg.FileName;
                }
            };
            saveGroup.Controls.Add(saveBrowse);

            saveCheckBtn.Text = "세이브 확인";
            saveCheckBtn.SetBounds(12, 92, 130, 30);
            saveCheckBtn.Click += delegate { StartSaveFix(false); };
            saveGroup.Controls.Add(saveCheckBtn);

            saveFixBtn.Text = "세이브 글자 고치기";
            saveFixBtn.SetBounds(152, 92, 170, 30);
            saveFixBtn.Click += delegate { StartSaveFix(true); };
            saveGroup.Controls.Add(saveFixBtn);

            saveAssemblyBtn.Text = "의원명 한국어화";
            saveAssemblyBtn.SetBounds(332, 92, 170, 30);
            saveAssemblyBtn.Click += delegate { StartAssemblyFix(); };
            saveGroup.Controls.Add(saveAssemblyBtn);

            Label assemblyHint = new Label();
            assemblyHint.Text = "※ 의원명 한국어화는 암호화된 PPSSPP/PSP 세이브도 직접 처리합니다.";
            assemblyHint.SetBounds(12, 126, 680, 22);
            saveGroup.Controls.Add(assemblyHint);

            bar.SetBounds(12, 342, 718, 18);
            Controls.Add(bar);

            logBox.SetBounds(12, 370, 718, 310);
            logBox.Multiline = true;
            logBox.ReadOnly = true;
            logBox.ScrollBars = ScrollBars.Vertical;
            logBox.Font = new Font("Consolas", 9F);
            Controls.Add(logBox);

            Log("일본판 원본 ISO 를 선택하고 [한국어화 적용]을 누르세요.");
            Log("원본: Makai Senki Disgaea 2 Portable (Japan) (PSP) (PSN).iso");
            Log("적용 전 원본 구간을 .d2bak 백업으로 남깁니다.");
            Log("DLC가 있으면 ULJS00183 폴더를 선택하세요. 없는 EDAT는 자동으로 건너뜁니다.");
            Log(string.Empty);
            Log("※ PPSSPP에서 검증했습니다. 실기(CFW)는 아직 검증되지 않았습니다.");
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
            saveCheckBtn.Enabled = saveFixBtn.Enabled = !busy;
            saveAssemblyBtn.Enabled = !busy;
        }

        private void Start(Mode mode)
        {
            string iso = isoBox.Text.Trim().Trim('"');
            string dlc = dlcBox.Text.Trim().Trim('"');
            if (iso.Length == 0) { MessageBox.Show(this, "ISO 를 선택하세요."); return; }
            if (dlc.Length > 0 && !Directory.Exists(dlc))
            {
                MessageBox.Show(this, "DLC 폴더를 찾을 수 없습니다:\n" + dlc);
                return;
            }
            SetBusy(true);
            SetProgress(0);
            logBox.Clear();
            Thread t = new Thread(delegate()
            {
                try
                {
                    if (dlc.Length == 0)
                        Run(iso, mode, Log, SetProgress);
                    else
                    {
                        Run(iso, mode, Log, delegate(int p) { SetProgress(p * 3 / 4); });
                        RunDlc(dlc, mode, Log, delegate(int p) { SetProgress(75 + p / 4); });
                    }
                }
                catch (Exception ex) { Log(string.Empty); Log("오류: " + ex.Message); }
                finally { SetBusy(false); }
            });
            t.IsBackground = true;
            t.Start();
        }

        private void StartSaveFix(bool apply)
        {
            string path = saveBox.Text.Trim().Trim('"');
            if (string.IsNullOrWhiteSpace(path))
            {
                MessageBox.Show(this, "세이브 파일(DATA.BIN)을 지정하세요.", "안내",
                                MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            if (apply)
            {
                DialogResult r = MessageBox.Show(
                    this,
                    "세이브 파일을 수정합니다.\n\n" +
                    "원본은 <파일이름>.d2bak 으로 백업합니다.\n" +
                    "한 번만 실행해야 하며, 두 번 고치면 글자가 다시 깨집니다.\n\n" +
                    "계속하시겠습니까?",
                    "세이브 글자 고치기", MessageBoxButtons.OKCancel,
                    MessageBoxIcon.Warning);
                if (r != DialogResult.OK) return;
            }

            SetBusy(true);
            SetProgress(0);
            logBox.Clear();
            Thread t = new Thread(delegate()
            {
                try { FixSave(path, apply, Log); }
                catch (Exception ex) { Log(string.Empty); Log("오류: " + ex.Message); }
                finally { SetBusy(false); SetProgress(100); }
            });
            t.IsBackground = true;
            t.Start();
        }

        private void StartAssemblyFix()
        {
            string path = saveBox.Text.Trim().Trim('"');
            if (string.IsNullOrWhiteSpace(path))
            {
                MessageBox.Show(this, "세이브 파일(DATA.BIN)을 지정하세요.", "안내",
                                MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            DialogResult r = MessageBox.Show(
                this,
                "기존 세이브에 저장된 암흑의회 의원명 64개를 한국어로 바꿉니다.\n\n" +
                "암호화 세이브는 PARAM.SFO도 함께 갱신하며, 원본 두 파일은 백업합니다.\n\n" +
                "계속하시겠습니까?",
                "의원명 한국어화", MessageBoxButtons.OKCancel,
                MessageBoxIcon.Warning);
            if (r != DialogResult.OK) return;

            SetBusy(true);
            SetProgress(0);
            logBox.Clear();
            Thread t = new Thread(delegate()
            {
                try { FixAssemblySave(path, true, Log); }
                catch (Exception ex) { Log(string.Empty); Log("오류: " + ex.Message); }
                finally { SetBusy(false); SetProgress(100); }
            });
            t.IsBackground = true;
            t.Start();
        }

        private void StartRestore()
        {
            string iso = isoBox.Text.Trim().Trim('"');
            string dlc = dlcBox.Text.Trim().Trim('"');
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
                try
                {
                    if (dlc.Length == 0)
                        RestoreFromBackup(iso, bk, Log, SetProgress);
                    else
                    {
                        RestoreFromBackup(iso, bk, Log,
                            delegate(int p) { SetProgress(p * 3 / 4); });
                        RunDlc(dlc, Mode.Restore, Log,
                            delegate(int p) { SetProgress(75 + p / 4); });
                    }
                }
                catch (Exception ex) { Log(string.Empty); Log("오류: " + ex.Message); }
                finally { SetBusy(false); }
            });
            t.IsBackground = true;
            t.Start();
        }
    }


    // ---------- 세이브 글자 복구 ----------
    //
    // 아이템 이름은 세이브에 **문자열로 저장**된다. v20260830 은 폰트 코드 위치가
    // 자동 재배치된 빌드였고, 그때 얻은 아이템은 그 시점 코드 바이트로 세이브에
    // 박혔다. v20260831 에서 코드 위치를 되돌렸으므로 그 바이트가 엉뚱한 글자로
    // 그려진다(젓례읖 맞토 = 정령의 망토). ISO·DLC 는 정상이다.
    //
    // ★ 대상은 **평문** 세이브다. PSP 세이브는 기본적으로 암호화되어 있어
    //   PPSSPP 설정에서 EncryptSave 를 끄고 새 슬롯에 저장한 파일이어야 한다.

    private static Dictionary<int, int> LoadSaveMap(Action<string> log)
    {
        string exeDir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        string[] cands = new string[]
        {
            string.IsNullOrEmpty(exeDir) ? SaveMapName : Path.Combine(exeDir, SaveMapName),
            Path.Combine(Directory.GetCurrentDirectory(), SaveMapName),
        };
        string path = null;
        foreach (string c in cands) if (File.Exists(c)) { path = c; break; }
        if (path == null)
            throw new FileNotFoundException(
                "세이브 복구 데이터가 없습니다: " + SaveMapName + "\n\n" +
                "patcher 폴더의 파일들을 함께 두세요.");

        using (FileStream fs = File.OpenRead(path))
        using (BinaryReader r = new BinaryReader(fs, Encoding.UTF8))
        {
            if (Encoding.ASCII.GetString(r.ReadBytes(SaveMapMagic.Length)) != SaveMapMagic)
                throw new InvalidDataException("세이브 복구 데이터 형식이 올바르지 않습니다.");
            r.ReadInt32();
            int tl = r.ReadUInt16();
            string title = Encoding.UTF8.GetString(r.ReadBytes(tl));
            log(title);
            int n = r.ReadInt32();
            Dictionary<int, int> map = new Dictionary<int, int>(n);
            for (int i = 0; i < n; i++)
            {
                int o1 = r.ReadByte(), o2 = r.ReadByte();
                int n1 = r.ReadByte(), n2 = r.ReadByte();
                map[(o1 << 8) | o2] = (n1 << 8) | n2;
            }
            log(string.Format(CultureInfo.InvariantCulture, "코드 매핑 {0:N0}쌍", map.Count));
            return map;
        }
    }

    // 암호화된 세이브인지 — 0x00 이 거의 없고 바이트 분포가 균일하면 암호문이다.
    private static bool LooksEncrypted(byte[] d)
    {
        if (d.Length == 0) return false;
        int[] c = new int[256];
        foreach (byte b in d) c[b]++;
        int distinct = 0;
        foreach (int v in c) if (v > 0) distinct++;
        double zero = (double)c[0] / d.Length;
        return zero < 0.03 && distinct > 250;
    }

    private static void FixSave(string path, bool apply, Action<string> log)
    {
        Dictionary<int, int> map = LoadSaveMap(log);
        log(string.Empty);

        if (!File.Exists(path))
            throw new FileNotFoundException("세이브를 찾을 수 없습니다: " + path);
        byte[] data = File.ReadAllBytes(path);
        log(string.Format(CultureInfo.InvariantCulture,
            "대상: {0} ({1:N0}B)", Path.GetFileName(path), data.Length));

        // ★★ 두 번 돌리면 세이브가 망가진다.
        //   구 코드표와 새 코드표는 대체로 같은 글자 집합의 **순열**이라, 어떤 글자의
        //   새 코드가 다른 글자의 구 코드와 겹친다. 그래서 한 번 고친 파일에 다시
        //   돌리면 또 바뀌어 버린다(검증에서 확인: 고친 뒤에도 "바꿀 글자 20자").
        //   백업 존재를 1회성 표시로 쓴다.
        string guardBak = path + ".d2bak";
        if (File.Exists(guardBak))
        {
            log(string.Empty);
            log("이 세이브는 이미 복구했습니다 (" + Path.GetFileName(guardBak) + " 있음).");
            log("두 번 고치면 글자가 다시 깨지므로 진행하지 않습니다.");
            log("처음 상태로 돌리려면 백업 파일을 되돌린 뒤 다시 시도하세요.");
            return;
        }

        if (LooksEncrypted(data))
            throw new InvalidDataException(
                "암호화된 세이브입니다 — 이 기능으로는 고칠 수 없습니다.\n\n" +
                "PPSSPP 설정에서 저장 데이터 암호화(EncryptSave)를 끄고,\n" +
                "게임에서 새 슬롯에 저장한 뒤 그 DATA.BIN 을 지정하세요.");

        // ★ 문자 경계를 지켜 치환한다. 바이트를 1칸씩 밀며 짝을 맞추면 인접 두
        //   글자에 걸친 쌍이 우연히 일치해 엉뚱한 글자로 바뀐다(검증에서 확인).
        //   한글 코드의 선행바이트는 0xF0~0xFC 이고 한 글자는 항상 2바이트다.
        int changed = 0, kept = 0;
        for (int i = 0; i < data.Length; )
        {
            byte b = data[i];
            if (b >= 0xF0 && b <= 0xFC && i + 1 < data.Length)
            {
                int key = (b << 8) | data[i + 1];
                int rep;
                if (map.TryGetValue(key, out rep))
                {
                    data[i] = (byte)(rep >> 8);
                    data[i + 1] = (byte)(rep & 0xFF);
                    changed++;
                }
                else kept++;
                i += 2;
            }
            else i += 1;
        }

        log(string.Format(CultureInfo.InvariantCulture,
            "바꿀 글자 {0:N0}자 / 그대로 둘 글자 {1:N0}자", changed, kept));

        if (changed == 0)
        {
            log(string.Empty);
            log("바꿀 것이 없습니다. 이미 정상이거나 대상이 아닌 세이브입니다.");
            return;
        }
        if (!apply)
        {
            log(string.Empty);
            log("확인만 했습니다. 실제로 고치려면 [세이브 글자 고치기] 를 누르세요.");
            return;
        }

        File.Copy(path, guardBak);
        log("백업: " + Path.GetFileName(guardBak));
        File.WriteAllBytes(path, data);
        log(string.Empty);
        log("완료. 세이브 글자를 복구했습니다.");
        log("게임에서 불러와 아이템 이름을 확인하세요.");
    }

    // ---------- 기존 세이브의 암흑의회 의원명 한국어화 ----------
    //
    // 의원 64명의 이름은 최초 생성 뒤 DATA.BIN 안에 문자열로 보존된다. 따라서
    // START_VM의 원본 이름표를 번역해도 이미 만들어진 세이브에는 소급되지 않는다.
    // 이 경로는 ULJS00183의 mode-5 게임 키로 암호화된 DATA.BIN을 복호화하고,
    // 32바이트 레코드 배열의 16바이트 이름 필드만 바꾼 뒤 PARAM.SFO까지 다시 만든다.

    private sealed class AssemblyMapEntry
    {
        public byte[] OldName;
        public byte[] NewName;
    }

    private static List<AssemblyMapEntry> LoadAssemblyMap(Action<string> log)
    {
        string path = SidecarPath(AssemblyMapName);
        using (FileStream fs = File.OpenRead(path))
        using (BinaryReader r = new BinaryReader(fs, Encoding.UTF8))
        {
            if (Encoding.ASCII.GetString(r.ReadBytes(AssemblyMapMagic.Length)) != AssemblyMapMagic)
                throw new InvalidDataException("의원명 치환표 형식이 올바르지 않습니다.");
            int version = r.ReadInt32();
            if (version != 1)
                throw new InvalidDataException("지원하지 않는 의원명 치환표 버전입니다: " + version);
            int count = r.ReadInt32();
            if (count != 64)
                throw new InvalidDataException("의원명 치환표가 64개가 아닙니다: " + count);
            List<AssemblyMapEntry> entries = new List<AssemblyMapEntry>(count);
            for (int i = 0; i < count; i++)
            {
                entries.Add(new AssemblyMapEntry
                {
                    OldName = r.ReadBytes(16),
                    NewName = r.ReadBytes(16),
                });
            }
            if (fs.Position != fs.Length)
                throw new InvalidDataException("의원명 치환표 뒤에 예상하지 못한 데이터가 있습니다.");
            log("의원명 치환표 64개 확인");
            return entries;
        }
    }

    private static bool BytesAt(byte[] data, int offset, byte[] needle)
    {
        if (offset < 0 || offset + needle.Length > data.Length) return false;
        for (int i = 0; i < needle.Length; i++)
            if (data[offset + i] != needle[i]) return false;
        return true;
    }

    private static int FindBytes(byte[] data, byte[] needle)
    {
        for (int at = 0; at + needle.Length <= data.Length; at++)
            if (BytesAt(data, at, needle)) return at;
        return -1;
    }

    private static bool SameBytes(byte[] a, byte[] b)
    {
        if (a.Length != b.Length) return false;
        for (int i = 0; i < a.Length; i++) if (a[i] != b[i]) return false;
        return true;
    }

    private static int PatchAssemblyNames(byte[] data, List<AssemblyMapEntry> map,
                                          Action<string> log)
    {
        const int stride = 0x20;
        int first = FindBytes(data, map[0].OldName);
        if (first < 0)
        {
            if (FindBytes(data, map[0].NewName) >= 0)
            {
                log("의원명은 이미 한국어로 변환되어 있습니다.");
                return 0;
            }
            throw new InvalidDataException(
                "의원명 배열을 찾지 못했습니다. ULJS00183의 정상 DATA.BIN인지 확인하세요.");
        }

        // 첫 이름 필드부터 0x20 간격으로 64개가 모두 원문과 맞아야만 수정한다.
        for (int i = 0; i < map.Count; i++)
        {
            int at = first + i * stride;
            if (!BytesAt(data, at, map[i].OldName))
                throw new InvalidDataException(
                    string.Format(CultureInfo.InvariantCulture,
                        "의원명 배열 구조가 예상과 다릅니다 ({0}/64, 0x{1:X}).", i + 1, at));
        }
        for (int i = 0; i < map.Count; i++)
            Buffer.BlockCopy(map[i].NewName, 0, data, first + i * stride, 16);

        log(string.Format(CultureInfo.InvariantCulture,
            "의원명 64/64 변환 (첫 필드 0x{0:X})", first));
        return map.Count;
    }

    private static void RunSaveCrypto(string arguments)
    {
        ProcessStartInfo info = new ProcessStartInfo();
        info.FileName = SidecarPath(SaveCryptoName);
        info.Arguments = arguments;
        info.UseShellExecute = false;
        info.CreateNoWindow = true;
        info.RedirectStandardOutput = true;
        info.RedirectStandardError = true;
        using (Process process = Process.Start(info))
        {
            string stdout = process.StandardOutput.ReadToEnd();
            string stderr = process.StandardError.ReadToEnd();
            process.WaitForExit();
            if (process.ExitCode != 0)
                throw new InvalidDataException(
                    "세이브 암복호화 실패(" + process.ExitCode + ")\n" + stdout + stderr);
        }
    }

    private static void FixAssemblySave(string path, bool apply, Action<string> log)
    {
        if (!File.Exists(path))
            throw new FileNotFoundException("세이브를 찾을 수 없습니다: " + path);
        if (!Path.GetFileName(path).Equals("DATA.BIN", StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("DATA.BIN 파일을 지정하세요.");

        List<AssemblyMapEntry> map = LoadAssemblyMap(log);
        byte[] source = File.ReadAllBytes(path);
        bool encrypted = LooksEncrypted(source);
        log(string.Format(CultureInfo.InvariantCulture,
            "대상: {0} ({1:N0}B, {2})", path, source.Length,
            encrypted ? "암호화" : "평문"));

        string tempDir = Path.Combine(Path.GetTempPath(), "D2SaveFix_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempDir);
        try
        {
            string plainPath = Path.Combine(tempDir, "plain.bin");
            string fixedPath = Path.Combine(tempDir, "fixed.bin");
            string keyPath = Path.Combine(tempDir, "key.bin");
            string encryptedPath = Path.Combine(tempDir, "DATA.BIN");
            string roundtripPath = Path.Combine(tempDir, "roundtrip.bin");
            string sfoOutPath = Path.Combine(tempDir, "PARAM.SFO");
            File.WriteAllBytes(keyPath, Encoding.ASCII.GetBytes(SaveCryptoKey));

            string sfoPath = Path.Combine(Path.GetDirectoryName(path), "PARAM.SFO");
            if (encrypted)
            {
                if (!File.Exists(sfoPath))
                    throw new FileNotFoundException("암호화 세이브와 같은 폴더에 PARAM.SFO가 없습니다.");
                RunSaveCrypto("-d " + Q(keyPath) + " 5 " + Q(path) + " " + Q(plainPath));
                log("mode 5 복호화 완료");
            }
            else
            {
                File.WriteAllBytes(plainPath, source);
            }

            byte[] plain = File.ReadAllBytes(plainPath);
            int changed = PatchAssemblyNames(plain, map, log);
            if (changed == 0) return;
            File.WriteAllBytes(fixedPath, plain);
            if (!apply)
            {
                log("확인만 했습니다. 실제 파일은 바꾸지 않았습니다.");
                return;
            }

            string dataBackup = path + ".d2assemblybak";
            string sfoBackup = sfoPath + ".d2assemblybak";
            if (File.Exists(dataBackup) || (encrypted && File.Exists(sfoBackup)))
                throw new InvalidDataException(
                    "의원명 백업이 이미 있어 중복 적용을 중단합니다.\n" + dataBackup);

            if (encrypted)
            {
                RunSaveCrypto("-e " + Q(keyPath) + " 5 " + Q(fixedPath) + " " +
                    Q(encryptedPath) + " DATA.BIN " + Q(sfoPath) + " " + Q(sfoOutPath));
                RunSaveCrypto("-d " + Q(keyPath) + " 5 " + Q(encryptedPath) + " " + Q(roundtripPath));
                if (!SameBytes(plain, File.ReadAllBytes(roundtripPath)))
                    throw new InvalidDataException("재암호화 왕복 검증이 일치하지 않습니다.");
                log("재암호화 및 왕복 검증 완료");

                File.Copy(path, dataBackup);
                File.Copy(sfoPath, sfoBackup);
                File.Copy(encryptedPath, path, true);
                File.Copy(sfoOutPath, sfoPath, true);
                log("백업: " + Path.GetFileName(dataBackup));
                log("백업: " + Path.GetFileName(sfoBackup));
            }
            else
            {
                File.Copy(path, dataBackup);
                File.Copy(fixedPath, path, true);
                log("백업: " + Path.GetFileName(dataBackup));
            }
            log(string.Empty);
            log("완료. 기존 암흑의회 의원명을 한국어로 바꿨습니다.");
            log("게임을 완전히 재시작한 뒤 정상 세이브로 불러와 확인하세요.");
        }
        finally
        {
            try { Directory.Delete(tempDir, true); } catch { }
        }
    }

    // ---------- 진입점 ----------

    [STAThread]
    private static int Main(string[] args)
    {
        bool cli = false;
        string iso = null;
        string dlc = null;
        string fixsave = null;
        bool fixsaveDry = false;
        string fixassembly = null;
        bool fixassemblyDry = false;
        Mode mode = Mode.Patch;
        for (int i = 0; i < args.Length; i++)
        {
            string a = args[i];
            if (a == "--cli") cli = true;
            else if (a == "--verify") { cli = true; mode = Mode.Verify; }
            else if (a == "--restore") { cli = true; mode = Mode.Restore; }
            else if (a == "--dlc" && i + 1 < args.Length)
            {
                cli = true;
                dlc = args[++i];
            }
            else if (a == "--fixsave" && i + 1 < args.Length)
            {
                cli = true;
                fixsave = args[++i];
            }
            else if (a == "--checksave" && i + 1 < args.Length)
            {
                cli = true;
                fixsave = args[++i];
                fixsaveDry = true;
            }
            else if (a == "--fixassembly" && i + 1 < args.Length)
            {
                cli = true;
                fixassembly = args[++i];
            }
            else if (a == "--checkassembly" && i + 1 < args.Length)
            {
                cli = true;
                fixassembly = args[++i];
                fixassemblyDry = true;
            }
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
            if (fixsave != null)
            {
                FixSave(fixsave, !fixsaveDry, Console.WriteLine);
                return 0;
            }
            if (fixassembly != null)
            {
                FixAssemblySave(fixassembly, !fixassemblyDry, Console.WriteLine);
                return 0;
            }
            if (iso == null)
            {
                Console.WriteLine(
                    "사용: D2_Korean_QuickPatch.exe <ISO> [--dlc <ULJS00183 폴더>] " +
                    "[--verify|--restore]\n" +
                    "      D2_Korean_QuickPatch.exe --checksave <DATA.BIN>   (확인만)\n" +
                    "      D2_Korean_QuickPatch.exe --fixsave <DATA.BIN>     (구 코드표 복구)\n" +
                    "      D2_Korean_QuickPatch.exe --checkassembly <DATA.BIN> (의원명 확인)\n" +
                    "      D2_Korean_QuickPatch.exe --fixassembly <DATA.BIN>   (의원명 한국어화)");
                return 2;
            }
            if (mode == Mode.Restore)
            {
                string backup = iso + ".d2bak";
                if (!File.Exists(backup))
                    throw new FileNotFoundException("ISO 백업을 찾을 수 없습니다: " + backup);
                RestoreFromBackup(iso, backup, Console.WriteLine, null);
                if (!string.IsNullOrWhiteSpace(dlc))
                    RunDlc(dlc, Mode.Restore, Console.WriteLine, null);
            }
            else
            {
                Run(iso, mode, Console.WriteLine, null);
                if (!string.IsNullOrWhiteSpace(dlc))
                    RunDlc(dlc, mode, Console.WriteLine, null);
            }
            return 0;
        }
        catch (Exception ex)
        {
            Console.WriteLine("오류: " + ex.Message);
            return 1;
        }
    }
}
