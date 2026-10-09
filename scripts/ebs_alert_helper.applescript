use framework "Foundation"
use scripting additions

-- Creates one reminder from the files study_alert.py writes. iCloud carries
-- it to the iPhone, which shows the alert a minute after creation.
property listName : "EBS 일본어 알림"

on read_utf8(file_path)
	set file_text to current application's NSString's stringWithContentsOfFile:file_path encoding:(current application's NSUTF8StringEncoding) |error|:(missing value)
	if file_text is missing value then error "Could not read " & file_path
	return file_text as text
end read_utf8

on save_result(status_path, the_message)
	set result_text to current application's NSString's stringWithString:(the_message & linefeed)
	result_text's writeToFile:status_path atomically:true encoding:(current application's NSUTF8StringEncoding) |error|:(missing value)
end save_result

on run
	set runtimeDir to (POSIX path of (path to home folder)) & "Library/Application Support/EBSPrivatePodcast/"
	set statusPath to runtimeDir & "alert_status.txt"
	try
		set alertTitle to paragraph 1 of my read_utf8(runtimeDir & "alert_title.txt")
		set alertBody to my read_utf8(runtimeDir & "alert_body.txt")
		set alertDate to (current date) + 60

		tell application "Reminders"
			if not (exists list listName) then
				make new list with properties {name:listName}
			end if
			tell list listName
				make new reminder with properties {name:alertTitle, body:alertBody, remind me date:alertDate}
			end tell
		end tell

		my save_result(statusPath, "OK " & alertTitle)
	on error errorMessage number errorNumber
		my save_result(statusPath, "ERROR " & errorNumber & " " & errorMessage)
	end try
end run
