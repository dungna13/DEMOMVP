$word = New-Object -ComObject Word.Application
$word.Visible = $false
$doc = $word.Documents.Open("C:\Users\Admin\Downloads\MVP\DocMind_Implementation_Plan.docx")
$doc.SaveAs("C:\Users\Admin\Downloads\MVP\DocMind_Implementation_Plan.txt", 2)
$doc.Close()
$word.Quit()
