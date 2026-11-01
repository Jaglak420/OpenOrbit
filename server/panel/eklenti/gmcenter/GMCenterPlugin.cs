using System;
using BepInEx;
using BepInEx.Unity.IL2CPP;

namespace OpenOrbit;

[BepInPlugin("openorbit.gmcenter", "OpenOrbit GM Center", "0.1.0")]
public sealed class GMCenterPlugin : BasePlugin
{
    public override void Load()
    {
        try
        {
            AddComponent<GMCenterOverlay>();
            Log.LogInfo("OpenOrbit GM Center loaded. Press F10 in game.");
        }
        catch (Exception e)
        {
            Log.LogError("OpenOrbit GM Center could not start: " + e);
        }
    }
}
