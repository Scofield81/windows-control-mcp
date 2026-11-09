param(
    [int]$Hwnd = 0,
    [string]$Name = '',
    [string]$AutomationId = '',
    [ValidateSet('find','properties','get_text','set_value','select','toggle','scroll','focus')]
    [string]$Operation = 'find',
    [string]$Value = ''
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

if ([string]::IsNullOrWhiteSpace($Name) -and [string]::IsNullOrWhiteSpace($AutomationId)) {
    throw 'Name vagy AutomationId szukseges.'
}

$root = if ($Hwnd -gt 0) {
    [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$Hwnd)
} else {
    [System.Windows.Automation.AutomationElement]::RootElement
}
if ($null -eq $root) { throw 'A megadott ablak nem talalhato.' }

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
if ($null -eq $element) { throw 'A keresett UI-elem nem talalhato.' }

$rect = $element.Current.BoundingRectangle
$base = [ordered]@{
    name = $element.Current.Name
    automation_id = $element.Current.AutomationId
    control_type = $element.Current.ControlType.ProgrammaticName
    class_name = $element.Current.ClassName
    hwnd = $element.Current.NativeWindowHandle
    enabled = $element.Current.IsEnabled
    offscreen = $element.Current.IsOffscreen
    left = Convert-BoundedInt $rect.Left
    top = Convert-BoundedInt $rect.Top
    right = Convert-BoundedInt $rect.Right
    bottom = Convert-BoundedInt $rect.Bottom
}

switch ($Operation) {
    'find' { $base.found = $true }
    'properties' {
        $base.found = $true
        $base.process_id = $element.Current.ProcessId
        $probe = $null
        $base.supports_invoke = $element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$probe)
        $probe = $null
        $base.supports_value = $element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$probe)
        $probe = $null
        $base.supports_text = $element.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$probe)
        $probe = $null
        $base.supports_selection_item = $element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$probe)
        $probe = $null
        $base.supports_toggle = $element.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$probe)
        $probe = $null
        $base.supports_scroll = $element.TryGetCurrentPattern([System.Windows.Automation.ScrollItemPattern]::Pattern, [ref]$probe)
    }
    'get_text' {
        $pattern = $null
        if ($element.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$pattern)) {
            $base.text = ([System.Windows.Automation.TextPattern]$pattern).DocumentRange.GetText(-1)
        } elseif ($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
            $base.text = ([System.Windows.Automation.ValuePattern]$pattern).Current.Value
        } else {
            $base.text = $element.Current.Name
        }
    }
    'set_value' {
        $pattern = $null
        if (-not $element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
            throw 'A UI-elem nem tamogat ValuePattern-t.'
        }
        ([System.Windows.Automation.ValuePattern]$pattern).SetValue($Value)
        $base.updated = $true
    }
    'select' {
        $pattern = $null
        if (-not $element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$pattern)) {
            throw 'A UI-elem nem tamogat SelectionItemPattern-t.'
        }
        ([System.Windows.Automation.SelectionItemPattern]$pattern).Select()
        $base.selected = $true
    }
    'toggle' {
        $pattern = $null
        if (-not $element.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$pattern)) {
            throw 'A UI-elem nem tamogat TogglePattern-t.'
        }
        ([System.Windows.Automation.TogglePattern]$pattern).Toggle()
        $base.toggled = $true
    }
    'scroll' {
        $pattern = $null
        if (-not $element.TryGetCurrentPattern([System.Windows.Automation.ScrollItemPattern]::Pattern, [ref]$pattern)) {
            throw 'A UI-elem nem tamogat ScrollItemPattern-t.'
        }
        ([System.Windows.Automation.ScrollItemPattern]$pattern).ScrollIntoView()
        $base.scrolled = $true
    }
    'focus' {
        $element.SetFocus()
        $base.focused = $true
    }
}

$base | ConvertTo-Json -Depth 5 -Compress
