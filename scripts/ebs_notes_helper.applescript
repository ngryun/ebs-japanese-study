use framework "Foundation"

property notesFolderName : "EBS 일본어 학습노트"
property titleFilePath : "/Volumes/Transcend/ebs_japan_radio/analysis_output/apple_notes_title.txt"
property bodyFilePath : "/Volumes/Transcend/ebs_japan_radio/analysis_output/apple_notes_body.html"
property statusFilePath : "/Volumes/Transcend/ebs_japan_radio/analysis_output/apple_notes_status.txt"

on read_utf8(file_path)
	set file_text to current application's NSString's stringWithContentsOfFile:file_path encoding:(current application's NSUTF8StringEncoding) |error|:(missing value)
	if file_text is missing value then error "Could not read " & file_path
	return file_text as text
end read_utf8

on save_result(the_message)
	set result_text to current application's NSString's stringWithString:(the_message & linefeed)
	result_text's writeToFile:(my statusFilePath) atomically:true encoding:(current application's NSUTF8StringEncoding) |error|:(missing value)
end save_result

on run
	try
		set noteTitle to paragraph 1 of my read_utf8(my titleFilePath)
		set noteBody to my read_utf8(my bodyFilePath)

		tell application "Notes"
			set iCloudAccount to first account whose name is "iCloud"
			tell iCloudAccount
				if not (exists folder notesFolderName) then
					make new folder with properties {name:notesFolderName}
				end if
				set targetFolder to folder notesFolderName
				set matchingNotes to every note of targetFolder whose name is noteTitle
				if (count of matchingNotes) > 0 then
					set body of item 1 of matchingNotes to noteBody
				else
					make new note at targetFolder with properties {body:noteBody}
				end if
			end tell
		end tell

		my save_result("OK " & noteTitle)
	on error errorMessage number errorNumber
		my save_result("ERROR " & errorNumber & " " & errorMessage)
	end try
end run
