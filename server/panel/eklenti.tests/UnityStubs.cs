using System;
namespace UnityEngine
{
    public class MonoBehaviour { public MonoBehaviour(IntPtr ptr) { } }
    public enum KeyCode { F10, Escape }
    public enum CursorLockMode { None, Locked, Confined }
    public struct Rect
    {
        public float x, y, width, height;
        public Rect(float x, float y, float width, float height)
        { this.x=x; this.y=y; this.width=width; this.height=height; }
    }
    public struct Vector2 { public float x, y; }
    public struct Color
    {
        public float r,g,b,a;
        public Color(float r,float g,float b,float a) { this.r=r; this.g=g; this.b=b; this.a=a; }
    }
    public class GUISkin { public object box = new object(); }
    public static class GUI
    {
        public static Color backgroundColor { get; set; }
        public static Color contentColor { get; set; }
        public static GUISkin skin { get; } = new GUISkin();
        public static Rect Window(int id, Rect rect, Action<int> draw, string title) { draw(id); return rect; }
        public static void DragWindow(Rect rect) { }
    }
    public static class GUILayout
    {
        public static object ExpandWidth(bool value) => new object();
        public static object ExpandHeight(bool value) => new object();
        public static object Width(float value) => new object();
        public static object Height(float value) => new object();
        public static void BeginVertical(params object[] options) { }
        public static void EndVertical() { }
        public static void BeginHorizontal(params object[] options) { }
        public static void EndHorizontal() { }
        public static void FlexibleSpace() { }
        public static void Space(float pixels) { }
        public static void Label(string text, params object[] options) { }
        public static bool Button(string text, params object[] options) => false;
        public static Vector2 BeginScrollView(Vector2 scroll, params object[] options) => scroll;
        public static void EndScrollView() { }
    }
    public static class Cursor
    {
        public static bool visible { get; set; }
        public static CursorLockMode lockState { get; set; }
    }
    public static class Input { public static bool GetKeyDown(KeyCode key) => false; }
    public static class Time { public static float unscaledTime => 0f; }
    public static class Screen { public static int width => 1920; public static int height => 1080; }
    public static class Mathf { public static float Clamp(float value, float min, float max) => Math.Max(min, Math.Min(value, max)); }
}

namespace BepInEx
{
    [AttributeUsage(AttributeTargets.Class)]
    public sealed class BepInPluginAttribute : Attribute
    {
        public BepInPluginAttribute(string guid, string name, string version) { }
    }
    public sealed class StubLog
    {
        public void LogInfo(object message) { }
        public void LogError(object message) { }
    }
}
namespace BepInEx.Unity.IL2CPP
{
    public abstract class BasePlugin
    {
        public abstract void Load();
        public BepInEx.StubLog Log { get; } = new BepInEx.StubLog();
        protected T AddComponent<T>() where T : UnityEngine.MonoBehaviour => default;
    }
}
