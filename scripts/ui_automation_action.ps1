param(
    [int]$Hwnd = 0,
    [string]$Name = '',
    [string]$AutomationId = '',
    [ValidateSet('invoke','toggle')][string]$Action = 'invoke'
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

if ([string]::IsNullOrWhiteSpace($Name) -and [string]::IsNullOrWhiteSpace($AutomationId)) {
    throw 'Name vagy AutomationId szükséges.'
}
$root = if ($Hwnd -gt 0) {
    [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$Hwnd)
} else {
    [System.Windows.Automation.AutomationElement]::RootElement
}
if ($null -eq $root) { throw 'A megadott ablak nem található.' }

$conditions = [System.Collections.Generic.List[System.Windows.Automation.Condition]]::new()
if (-not [string]::IsNullOrWhiteSpace($Name)) {
    $conditions.Add([System.Windows.Automation.PropertyCondition]::new(
        [System.Windows.Automation.AutomationElement]::NameProperty, $Name))
}
if (-not [string]::IsNullOrWhiteSpace($AutomationId)) {
    $conditions.Add([System.Windows.Automation.PropertyCondition]::new(
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty, $AutomationId))
}
$condition = if ($conditions.Count -eq 1) { $conditions[0] } else {
    [System.Windows.Automation.AndCondition]::new($conditions.ToArray())
}
$element = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
if ($null -eq $element) { throw 'A keresett UI-elem nem található.' }

if ($Action -eq 'invoke') {
    $pattern = $element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    ([System.Windows.Automation.InvokePattern]$pattern).Invoke()
} else {
    $pattern = $element.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
    ([System.Windows.Automation.TogglePattern]$pattern).Toggle()
}

$rect = $element.Current.BoundingRectangle
[ordered]@{
    action = $Action
    name = $element.Current.Name
    automation_id = $element.Current.AutomationId
    control_type = $element.Current.ControlType.ProgrammaticName
    hwnd = $element.Current.NativeWindowHandle
    left = [int]$rect.Left
    top = [int]$rect.Top
    right = [int]$rect.Right
    bottom = [int]$rect.Bottom
    invoked = $true
} | ConvertTo-Json -Depth 4 -Compress
