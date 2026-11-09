param(
    [int]$Hwnd = 0,
    [int]$MaxNodes = 200
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Convert-BoundedInt([double]$Number) {
    if ([double]::IsNaN($Number) -or [double]::IsInfinity($Number)) { return 0 }
    if ($Number -gt [int]::MaxValue) { return [int]::MaxValue }
    if ($Number -lt [int]::MinValue) { return [int]::MinValue }
    return [int]$Number
}

$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$Hwnd)
if ($null -eq $root) { throw "A megadott ablak nem található." }

# Do not call FindAll over the complete descendant tree and truncate later.
# A TreeWalker stops as soon as MaxNodes is reached, which is important for
# large Office/browser trees and remote sessions.
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
$pending = [System.Collections.Generic.Queue[System.Windows.Automation.AutomationElement]]::new()
$first = $walker.GetFirstChild($root)
while ($null -ne $first) {
    $pending.Enqueue($first)
    $first = $walker.GetNextSibling($first)
}
$result = [System.Collections.Generic.List[object]]::new()
$visited = 0
while ($pending.Count -gt 0 -and $visited -lt $MaxNodes) {
    $element = $pending.Dequeue()
    $visited++
    $child = $walker.GetFirstChild($element)
    while ($null -ne $child) {
        $pending.Enqueue($child)
        $child = $walker.GetNextSibling($child)
    }
    $rect = $element.Current.BoundingRectangle
    $result.Add([ordered]@{
        name = $element.Current.Name
        control_type = $element.Current.ControlType.ProgrammaticName
        automation_id = $element.Current.AutomationId
        class_name = $element.Current.ClassName
        hwnd = $element.Current.NativeWindowHandle
        enabled = $element.Current.IsEnabled
        left = Convert-BoundedInt $rect.Left
        top = Convert-BoundedInt $rect.Top
        right = Convert-BoundedInt $rect.Right
        bottom = Convert-BoundedInt $rect.Bottom
    })
}

[ordered]@{
    root_name = $root.Current.Name
    root_control_type = $root.Current.ControlType.ProgrammaticName
    returned = $result.Count
    truncated = ($pending.Count -gt 0)
    elements = $result
} | ConvertTo-Json -Depth 5 -Compress
