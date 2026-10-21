using System;
using System.Diagnostics;
using System.IO;
using System.Net.Sockets;
using System.Threading;
using System.Windows.Forms;

namespace SystemizeLauncher
{
    static class Program
    {
        [STAThread]
        static void Main()
        {
            string appDir = AppDomain.CurrentDomain.BaseDirectory;
            string pyExe = Path.Combine(appDir, "runtime\\python.exe");
            string appUrl = "http://127.0.0.1:8000";

            // 1. If server is already running, just open browser and exit
            if (IsPortListening("127.0.0.1", 8000))
            {
                OpenUrl(appUrl);
                return;
            }

            // 2. Fallback to system python if runtime\python.exe doesn't exist
            if (!File.Exists(pyExe))
            {
                pyExe = "python.exe";
            }

            // 3. Launch python server directly, completely hidden (Zero Terminal / Instant Launch)
            try
            {
                string manageTarget = File.Exists(Path.Combine(appDir, "manage.pyc")) ? "manage.pyc" : "manage.py";
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = pyExe;
                psi.Arguments = "-s \"" + manageTarget + "\" runserver 0.0.0.0:8000 --noreload";
                psi.WorkingDirectory = appDir;
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                psi.WindowStyle = ProcessWindowStyle.Hidden;
                psi.EnvironmentVariables["PYTHONUTF8"] = "1";
                psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";

                Process proc = Process.Start(psi);

                // 4. Poll until port 8000 is listening (max 20 seconds)
                bool connected = false;
                for (int i = 0; i < 40; i++)
                {
                    Thread.Sleep(500);
                    if (IsPortListening("127.0.0.1", 8000))
                    {
                        connected = true;
                        break;
                    }
                }

                // 5. Open browser
                OpenUrl(appUrl);
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "حدث خطأ أثناء تشغيل سيرفر Systemize:\n" + ex.Message,
                    "Systemize Gym OS",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
            }
        }

        static bool IsPortListening(string host, int port)
        {
            try
            {
                using (TcpClient client = new TcpClient())
                {
                    IAsyncResult result = client.BeginConnect(host, port, null, null);
                    bool success = result.AsyncWaitHandle.WaitOne(300);
                    if (success && client.Connected)
                    {
                        client.EndConnect(result);
                        return true;
                    }
                }
            }
            catch { }
            return false;
        }

        static void OpenUrl(string url)
        {
            try
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = url,
                    UseShellExecute = true
                });
            }
            catch { }
        }
    }
}
