print("Lua script loaded")

local SECRET = os.getenv("CARE_RADIOLOGY_WEBHOOK_SECRET")
print("Secret loaded: " .. tostring(SECRET ~= nil))

local studyCache = {}

function OnStoredInstance(instanceId, tags, metadata)
  local studyUID = tags["StudyInstanceUID"]
  local patientID = tags["PatientID"]

  if studyUID and not studyCache[studyUID] then
    studyCache[studyUID] = patientID
  end
end

function OnStableStudy(studyId, tags, metadata)
  print("OnStableStudy triggered")

  local studyUID = tags["StudyInstanceUID"]
  local patientID = studyCache[studyUID] or tags["PatientID"]
  local payload = [[
{
  "study_id": "]] .. (studyUID or "") .. [[",
  "patient_id": "]] .. (patientID or "") .. [["
}
]]

  print("Sending webhook request")

  local ok, err = pcall(function()
    HttpPost(
      "http://care-backend-1:9000/api/care_radiology/webhooks/study/",
      payload,
      {
        ["Content-Type"] = "application/json",
        ["Authorization"] = SECRET
      }
    )
  end)

  if ok then
    print("Webhook POST success")
  else
    print("Webhook POST FAILED: " .. tostring(err))
  end

  -- cleanup cache (must stay inside function)
  if studyUID then
    studyCache[studyUID] = nil
  end
end
