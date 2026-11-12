<?xml version="1.0" encoding="utf-8"?>
<productionProgram>
  <headerData>
    <targetMachine>ISS</targetMachine>
    <editMachine>ISS</editMachine>
    <lastEdit>2026-11-05T09:30:00-06:00</lastEdit>
    <lineConfiguration>
      <lineName id="1">Line</lineName>
    </lineConfiguration>
    <headPwb total="1" completion="1" />
    <headPlacement total="66" completion="0" />
    <headComponent total="34" completion="0" />
  </headerData>
  <core>
    <pwbData>
      <pwbId>Panel</pwbId>
      <pwbBasic>
        <referenceSide>FRONT</referenceSide>
        <transferDirection>LTOR</transferDirection>
        <referenceType>SHAPE</referenceType>
        <circuitType>STANDARD</circuitType>
        <bocMarkSelect>ALL</bocMarkSelect>
        <markRecognition>GRAYSCALE</markRecognition>
        <badMarkType>STANDARD</badMarkType>
        <badMarkRecognition>POSITIVE</badMarkRecognition>
      </pwbBasic>
      <pwbConfiguration>
        <outline x="256.0096" y="182.626" />
        <pwbThick thick="1.6" />
        <backHeight height="37" />
        <pwbHeight height="0" />
      </pwbConfiguration>
      <circuitConfigurationData>
        <circuitConfiguration index="0">
          <circuitUse>USE</circuitUse>
          <circuitId>A</circuitId>
          <circuitConfiguration>NONMATRIX</circuitConfiguration>
          <bocMarkType>PWBBOC</bocMarkType>
          <circuitOutline x="50.8" y="52.07" />
          <referencePosition />
          <nonMatrix>
            <totalCount count="15" />
            <allocation index="0" x="0" y="0" angle="0" rangeOver="0" />
            <allocation index="1" x="0" y="-52.578" angle="0" rangeOver="0" />
            <allocation index="2" x="0" y="-105.156" angle="0" rangeOver="0" />
            <allocation index="3" x="-51.308" y="0" angle="0" rangeOver="0" />
            <allocation index="4" x="-51.308" y="-52.578" angle="0" rangeOver="0" />
            <allocation index="5" x="-51.308" y="-105.156" angle="0" rangeOver="0" />
            <allocation index="6" x="-102.616" y="0" angle="0" rangeOver="0" />
            <allocation index="7" x="-102.616" y="-52.578" angle="0" rangeOver="0" />
            <allocation index="8" x="-102.616" y="-105.156" angle="0" rangeOver="0" />
            <allocation index="9" x="-153.924" y="0" angle="0" rangeOver="0" />
            <allocation index="10" x="-153.924" y="-52.578" angle="0" rangeOver="0" />
            <allocation index="11" x="-153.924" y="-105.156" angle="0" rangeOver="0" />
            <allocation index="12" x="-205.232" y="0" angle="0" rangeOver="0" />
            <allocation index="13" x="-205.232" y="-52.578" angle="0" rangeOver="0" />
            <allocation index="14" x="-205.232" y="-105.156" angle="0" rangeOver="0" />
          </nonMatrix>
        </circuitConfiguration>
        <circuitConfiguration index="1">
          <circuitUse>NOUSE</circuitUse>
          <circuitId>B</circuitId>
          <circuitConfiguration>SINGLE</circuitConfiguration>
          <bocMarkType>NOUSE</bocMarkType>
          <circuitOutline />
          <referencePosition />
        </circuitConfiguration>
      </circuitConfigurationData>
    </pwbData>
    <placementData>
      <placement index="0">
        <placementId>R35</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1001</componentName>
        <placementPosition x="41.783" y="21.209" rangeOver="False" />
        <placementAngle angle="180" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="1">
        <placementId>R30</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-2002</componentName>
        <placementPosition x="30.607" y="49.022" rangeOver="False" />
        <placementAngle angle="0" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="2">
        <placementId>R27</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1001</componentName>
        <placementPosition x="47.625" y="36.322" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="3">
        <placementId>D12</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>109821</componentName>
        <placementPosition x="33.401" y="20.574" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="4">
        <placementId>R34</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1001</componentName>
        <placementPosition x="37.846" y="22.606" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="5">
        <placementId>R33</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-2201</componentName>
        <placementPosition x="45.085" y="21.209" rangeOver="False" />
        <placementAngle angle="0" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="6">
        <placementId>FB2</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>109822</componentName>
        <placementPosition x="31.369" y="43.18" rangeOver="False" />
        <placementAngle angle="0" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="7">
        <placementId>D11</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107055-2</componentName>
        <placementPosition x="28.956" y="25.908" rangeOver="False" />
        <placementAngle angle="0" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="8">
        <placementId>D10</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>101672-4</componentName>
        <placementPosition x="11.43" y="3.81" rangeOver="False" />
        <placementAngle angle="180" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="9">
        <placementId>R29</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1003</componentName>
        <placementPosition x="30.5816" y="50.4698" rangeOver="False" />
        <placementAngle angle="180" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="10">
        <placementId>D1</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>101672-4</componentName>
        <placementPosition x="16.51" y="38.862" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="11">
        <placementId>C4</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>PP-5927-6</componentName>
        <placementPosition x="32.512" y="29.845" rangeOver="False" />
        <placementAngle angle="180" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="12">
        <placementId>U2</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>109824</componentName>
        <placementPosition x="10.668" y="46.355" rangeOver="False" />
        <placementAngle angle="180" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="13">
        <placementId>R5</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1001</componentName>
        <placementPosition x="13.1572" y="49.276" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="14">
        <placementId>R4</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1002</componentName>
        <placementPosition x="14.0328" y="43.9928" rangeOver="False" />
        <placementAngle angle="180" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="15">
        <placementId>R32</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1001</componentName>
        <placementPosition x="41.91" y="30.226" rangeOver="False" />
        <placementAngle angle="270" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="16">
        <placementId>F1</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>106238-2</componentName>
        <placementPosition x="11.303" y="38.989" rangeOver="False" />
        <placementAngle angle="270" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="17">
        <placementId>D9</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>109820</componentName>
        <placementPosition x="27.9146" y="43.2309" rangeOver="False" />
        <placementAngle angle="0" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="18">
        <placementId>D6</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>PP-5975-12</componentName>
        <placementPosition x="18.161" y="3.556" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="19">
        <placementId>R26</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1001</componentName>
        <placementPosition x="30.099" y="21.209" rangeOver="False" />
        <placementAngle angle="270" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="20">
        <placementId>R7</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1002</componentName>
        <placementPosition x="37.846" y="27.686" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="21">
        <placementId>R2</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1003</componentName>
        <placementPosition x="4.445" y="30.099" rangeOver="False" />
        <placementAngle angle="0" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="22">
        <placementId>Q1</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107053-3</componentName>
        <placementPosition x="4.191" y="32.893" rangeOver="False" />
        <placementAngle angle="180" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="23">
        <placementId>D2</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>PP-5975-13</componentName>
        <placementPosition x="9.779" y="30.861" rangeOver="False" />
        <placementAngle angle="180" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="24">
        <placementId>R14</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1002</componentName>
        <placementPosition x="38.354" y="12.446" rangeOver="False" />
        <placementAngle angle="0" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="25">
        <placementId>R13</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1002</componentName>
        <placementPosition x="38.354" y="10.922" rangeOver="False" />
        <placementAngle angle="0" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="26">
        <placementId>R3</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-2212</componentName>
        <placementPosition x="26.924" y="46.482" rangeOver="False" />
        <placementAngle angle="270" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="27">
        <placementId>R1</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-8872</componentName>
        <placementPosition x="28.448" y="46.482" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="28">
        <placementId>L1</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>103094-2</componentName>
        <placementPosition x="24.892" y="37.338" rangeOver="False" />
        <placementAngle angle="0" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="29">
        <placementId>C6</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107523-1156-1003</componentName>
        <placementPosition x="17.145" y="48.768" rangeOver="False" />
        <placementAngle angle="270" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="30">
        <placementId>C5</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107523-1156-2204</componentName>
        <placementPosition x="19.685" y="48.768" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="31">
        <placementId>C3</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107523-1126-2205</componentName>
        <placementPosition x="25.527" y="32.1311" rangeOver="False" />
        <placementAngle angle="180" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="32">
        <placementId>R31</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1001</componentName>
        <placementPosition x="33.528" y="35.814" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="33">
        <placementId>R22</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1001</componentName>
        <placementPosition x="38.354" y="16.002" rangeOver="False" />
        <placementAngle angle="0" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="34">
        <placementId>C17</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107523-3156-1003</componentName>
        <placementPosition x="46.228" y="36.322" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="35">
        <placementId>R24</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1001</componentName>
        <placementPosition x="45.593" y="45.2121" rangeOver="False" />
        <placementAngle angle="180" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="36">
        <placementId>D8</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>109818</componentName>
        <placementPosition x="42.799" y="45.2121" rangeOver="False" />
        <placementAngle angle="0" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="37">
        <placementId>D7</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>109819</componentName>
        <placementPosition x="43.561" y="24.003" rangeOver="False" />
        <placementAngle angle="0" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="38">
        <placementId>C16</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107523-3156-1003</componentName>
        <placementPosition x="39.624" y="44.069" rangeOver="False" />
        <placementAngle angle="0" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="39">
        <placementId>R21</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1001</componentName>
        <placementPosition x="40.906" y="14.224" rangeOver="False" />
        <placementAngle angle="0" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="40">
        <placementId>R20</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1001</componentName>
        <placementPosition x="39.612" y="45.974" rangeOver="False" />
        <placementAngle angle="180" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="41">
        <placementId>R23</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1001</componentName>
        <placementPosition x="30.099" y="7.366" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="42">
        <placementId>R25</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1001</componentName>
        <placementPosition x="32.004" y="35.814" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="43">
        <placementId>C1</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107523-1156-1003</componentName>
        <placementPosition x="23.495" y="43.3071" rangeOver="False" />
        <placementAngle angle="0" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="44">
        <placementId>R28</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1002</componentName>
        <placementPosition x="45.593" y="42.926" rangeOver="False" />
        <placementAngle angle="180" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="45">
        <placementId>R8</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1001</componentName>
        <placementPosition x="38.354" y="14.224" rangeOver="False" />
        <placementAngle angle="180" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="46">
        <placementId>R19</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1003</componentName>
        <placementPosition x="28.702" y="21.209" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="47">
        <placementId>D5</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>109818</componentName>
        <placementPosition x="40.894" y="16.764" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="48">
        <placementId>C11</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107523-3156-1003</componentName>
        <placementPosition x="26.543" y="6.35" rangeOver="False" />
        <placementAngle angle="270" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="49">
        <placementId>U3</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>109825</componentName>
        <placementPosition x="30.353" y="13.589" rangeOver="False" />
        <placementAngle angle="270" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="50">
        <placementId>U4</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>109826</componentName>
        <placementPosition x="39.884" y="37.8306" rangeOver="False" />
        <placementAngle angle="0" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="51">
        <placementId>U1</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>109823</componentName>
        <placementPosition x="22.987" y="46.4821" rangeOver="False" />
        <placementAngle angle="180" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="52">
        <placementId>R18</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1002</componentName>
        <placementPosition x="38.354" y="17.526" rangeOver="False" />
        <placementAngle angle="0" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="53">
        <placementId>R17</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-11-1107</componentName>
        <placementPosition x="24.638" y="7.112" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="54">
        <placementId>R16</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-31-1002</componentName>
        <placementPosition x="34.671" y="7.366" rangeOver="False" />
        <placementAngle angle="270" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="55">
        <placementId>R15</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107522-11-1107</componentName>
        <placementPosition x="24.638" y="20.32" rangeOver="False" />
        <placementAngle angle="270" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="56">
        <placementId>D4</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>109817-2</componentName>
        <placementPosition x="17.145" y="26.797" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="57">
        <placementId>D3</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>109817-1</componentName>
        <placementPosition x="7.239" y="38.989" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="58">
        <placementId>C13</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107523-3156-1003</componentName>
        <placementPosition x="34.036" y="17.526" rangeOver="False" />
        <placementAngle angle="180" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="59">
        <placementId>C8</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107523-6156-1005</componentName>
        <placementPosition x="21.336" y="3.556" rangeOver="False" />
        <placementAngle angle="270" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="60">
        <placementId>C9</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107523-6156-1005</componentName>
        <placementPosition x="21.59" y="24.384" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="61">
        <placementId>C12</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107523-3156-2202</componentName>
        <placementPosition x="32.512" y="6.604" rangeOver="False" />
        <placementAngle angle="180" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="62">
        <placementId>C15</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107523-3156-4704</componentName>
        <placementPosition x="34.671" y="10.1721" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="63">
        <placementId>C10</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107523-3156-1003</componentName>
        <placementPosition x="26.543" y="21.209" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="64">
        <placementId>C14</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107523-3156-1003</componentName>
        <placementPosition x="32.512" y="8.128" rangeOver="False" />
        <placementAngle angle="180" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="65">
        <placementId>C2</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>107523-1126-2205</componentName>
        <placementPosition x="25.527" y="29.8451" rangeOver="False" />
        <placementAngle angle="180" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
    </placementData>
    <componentData>
      <component index="0">
        <componentBasic>
          <componentName>107522-31-1001</componentName>
          <comment>RESISTOR_1K_1%_0603</comment>
          <componentSize witdh="1.7" length="0.9" height="0.5512" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="1">
        <componentBasic>
          <componentName>107522-31-2002</componentName>
          <comment>RESISTOR_20K_0603_1%</comment>
          <componentSize witdh="1.7" length="0.9" height="0" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="2">
        <componentBasic>
          <componentName>109821</componentName>
          <comment>SCHOTTKY_DIODE_SOT23</comment>
          <componentSize witdh="1.4" length="3" height="1.0998" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="3">
        <componentBasic>
          <componentName>107522-31-2201</componentName>
          <comment>RC0603FR-132K2L</comment>
          <componentSize witdh="1.7" length="0.9" height="0" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="4">
        <componentBasic>
          <componentName>109822</componentName>
          <comment>FERRITE_BEAD_30_OHM_@_100_MHZ_1500MA_0603</comment>
          <componentSize witdh="1.6" length="0.8" height="0" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="5">
        <componentBasic>
          <componentName>107055-2</componentName>
          <comment>NRVB130LSFT1G</comment>
          <componentSize witdh="3.6" length="1.65" height="1.0008" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="6">
        <componentBasic>
          <componentName>101672-4</componentName>
          <comment>SS34-E3/9AT</comment>
          <componentSize witdh="7.94" length="5.905" height="1.0008" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="7">
        <componentBasic>
          <componentName>107522-31-1003</componentName>
          <comment>RESISTOR_100K_1%_0603</comment>
          <componentSize witdh="1.7" length="0.9" height="0" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="8">
        <componentBasic>
          <componentName>PP-5927-6</componentName>
          <comment>EEE-HB1V100R</comment>
          <componentSize witdh="6" length="5.3" height="0" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="9">
        <componentBasic>
          <componentName>109824</componentName>
          <comment>TPS1H200AQDGNRQ1</comment>
          <componentSize witdh="4.9251" length="3" height="0" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="10">
        <componentBasic>
          <componentName>107522-31-1002</componentName>
          <comment>RESISTOR_10K_1%_0603</comment>
          <componentSize witdh="1.7" length="0.9" height="0.5512" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="11">
        <componentBasic>
          <componentName>106238-2</componentName>
          <comment>MF-MSMF110/24X-2</comment>
          <componentSize witdh="4.6" length="3.24" height="1.6002" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="12">
        <componentBasic>
          <componentName>109820</componentName>
          <comment>ZENER_DIODE_5.1V_0.225W_SOT-23-3</comment>
          <componentSize witdh="1.3" length="2.92" height="1.11" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="13">
        <componentBasic>
          <componentName>PP-5975-12</componentName>
          <comment>ZENER_DIODE_0.5W_28V</comment>
          <componentSize witdh="2.69" length="1.6" height="1.3487" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="14">
        <componentBasic>
          <componentName>107053-3</componentName>
          <comment>NTR4171PT1G</comment>
          <componentSize witdh="1.3" length="2.92" height="1.11" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="15">
        <componentBasic>
          <componentName>PP-5975-13</componentName>
          <comment>1SMB5920BT3G</comment>
          <componentSize witdh="4.6" length="3.95" height="2.4206" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="16">
        <componentBasic>
          <componentName>107522-31-2212</componentName>
          <comment>CRCW060322K1FKEA</comment>
          <componentSize witdh="1.65" length="0.95" height="0" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="17">
        <componentBasic>
          <componentName>107522-31-8872</componentName>
          <comment>CRCW060388K7FKEA</comment>
          <componentSize witdh="1.65" length="0.95" height="0" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="18">
        <componentBasic>
          <componentName>103094-2</componentName>
          <comment>744777118</comment>
          <componentSize witdh="7.3" length="7.3" height="4.5009" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="19">
        <componentBasic>
          <componentName>107523-1156-1003</componentName>
          <comment>CC1206KRX7R9BB104</comment>
          <componentSize witdh="3.2" length="1.6" height="5.0013" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="20">
        <componentBasic>
          <componentName>107523-1156-2204</componentName>
          <comment>C1206C225K5RACTU</comment>
          <componentSize witdh="3.4" length="1.8" height="1.8009" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="21">
        <componentBasic>
          <componentName>107523-1126-2205</componentName>
          <comment>1206ZC226KAT2A</comment>
          <componentSize witdh="3.2" length="1.6" height="5.0013" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="22">
        <componentBasic>
          <componentName>107523-3156-1003</componentName>
          <comment>CAP_0603_50V</comment>
          <componentSize witdh="1.6" length="0.8" height="0" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="23">
        <componentBasic>
          <componentName>109818</componentName>
          <comment>LTST-C190KRKT</comment>
          <componentSize witdh="1.6" length="0.8001" height="0" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="24">
        <componentBasic>
          <componentName>109819</componentName>
          <comment>FULL_COLOR_REVERSE_MOUNT_WATERCLEAR_SMD_LED</comment>
          <componentSize witdh="3.2" length="1.6" height="1.2497" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="25">
        <componentBasic>
          <componentName>109825</componentName>
          <comment>TMC2209-LA</comment>
          <componentSize witdh="5" length="5" height="0" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="26">
        <componentBasic>
          <componentName>109826</componentName>
          <comment>ATMEGA4808-AFR</comment>
          <componentSize witdh="9.0177" length="9.0177" height="0" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="27">
        <componentBasic>
          <componentName>109823</componentName>
          <comment>LMR50410YQDBVRQ1</comment>
          <componentSize witdh="2.8" length="2.9" height="0" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="28">
        <componentBasic>
          <componentName>107522-11-1107</componentName>
          <comment>MCR18EZHFLR110</comment>
          <componentSize witdh="3.2" length="1.6" height="0" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="29">
        <componentBasic>
          <componentName>109817-2</componentName>
          <comment>SMAJ26CA</comment>
          <componentSize witdh="5.105" length="2.665" height="0" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="30">
        <componentBasic>
          <componentName>109817-1</componentName>
          <comment>SMBJ24CA-E3/52</comment>
          <componentSize witdh="5.01" length="3.94" height="2.4409" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="31">
        <componentBasic>
          <componentName>107523-6156-1005</componentName>
          <comment>UMK325BJ106MM-T</comment>
          <componentSize witdh="3.5" length="2.7" height="2.7" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="32">
        <componentBasic>
          <componentName>107523-3156-2202</componentName>
          <comment>CC0603KRX7R9BB223</comment>
          <componentSize witdh="1.6" length="0.8" height="0" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="33">
        <componentBasic>
          <componentName>107523-3156-4704</componentName>
          <comment>CAP_CER_4.7UF_16V_X7R_0603</comment>
          <componentSize witdh="1.6" length="0.8" height="0" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
    </componentData>
  </core>
  <model>
    <pwbData>
      <pwbId>Panel</pwbId>
      <pwbBasic>
        <pwbMaterial>EPOXY</pwbMaterial>
        <vacuumTable>NOUSE</vacuumTable>
        <traceability>TwoDimensions</traceability>
      </pwbBasic>
      <pwbConfiguration>
        <pwbLayoutOffset x="50.8" y="-117.8571" />
        <referencePosition x="0" y="0" />
        <clampOffset y="91.313" />
      </pwbConfiguration>
      <circuitConfigurationData>
        <circuitConfiguration index="0">
          <circuitId>A</circuitId>
          <circuitLayoutOffset x="0" y="0" />
        </circuitConfiguration>
        <circuitConfiguration index="1">
          <circuitId>B</circuitId>
          <circuitLayoutOffset x="0" y="0" />
        </circuitConfiguration>
      </circuitConfigurationData>
    </pwbData>
    <placementData>
      <placement index="0">
        <placementId>R35</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="1">
        <placementId>R30</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="2">
        <placementId>R27</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="3">
        <placementId>D12</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="4">
        <placementId>R34</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="5">
        <placementId>R33</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="6">
        <placementId>FB2</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="7">
        <placementId>D11</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="8">
        <placementId>D10</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="9">
        <placementId>R29</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="10">
        <placementId>D1</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="11">
        <placementId>C4</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="12">
        <placementId>U2</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="13">
        <placementId>R5</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="14">
        <placementId>R4</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="15">
        <placementId>R32</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="16">
        <placementId>F1</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="17">
        <placementId>D9</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="18">
        <placementId>D6</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="19">
        <placementId>R26</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="20">
        <placementId>R7</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="21">
        <placementId>R2</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="22">
        <placementId>Q1</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="23">
        <placementId>D2</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="24">
        <placementId>R14</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="25">
        <placementId>R13</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="26">
        <placementId>R3</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="27">
        <placementId>R1</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="28">
        <placementId>L1</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="29">
        <placementId>C6</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="30">
        <placementId>C5</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="31">
        <placementId>C3</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="32">
        <placementId>R31</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="33">
        <placementId>R22</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="34">
        <placementId>C17</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="35">
        <placementId>R24</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="36">
        <placementId>D8</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="37">
        <placementId>D7</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="38">
        <placementId>C16</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="39">
        <placementId>R21</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="40">
        <placementId>R20</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="41">
        <placementId>R23</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="42">
        <placementId>R25</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="43">
        <placementId>C1</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="44">
        <placementId>R28</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="45">
        <placementId>R8</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="46">
        <placementId>R19</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="47">
        <placementId>D5</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="48">
        <placementId>C11</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="49">
        <placementId>U3</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="50">
        <placementId>U4</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="51">
        <placementId>U1</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="52">
        <placementId>R18</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="53">
        <placementId>R17</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="54">
        <placementId>R16</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="55">
        <placementId>R15</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="56">
        <placementId>D4</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="57">
        <placementId>D3</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="58">
        <placementId>C13</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="59">
        <placementId>C8</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="60">
        <placementId>C9</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="61">
        <placementId>C12</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="62">
        <placementId>C15</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="63">
        <placementId>C10</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="64">
        <placementId>C14</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="65">
        <placementId>C2</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
    </placementData>
  </model>
  <machine>
    <bocMarkData>
      <circuitData index="0">
        <bocMark no="1">
          <markType>BOC</markType>
          <markName>BOCMARK01</markName>
          <solderType>standard</solderType>
          <effectiveCount count="3" />
          <fiducialMarkData>
            <fiducialMark index="0">
              <markName>F1</markName>
              <markPosition x="38.097" y="-111.5057" />
            </fiducialMark>
            <fiducialMark index="1">
              <markName>F2</markName>
              <markPosition x="38.097" y="58.4175" />
            </fiducialMark>
            <fiducialMark index="2">
              <markName>F3</markName>
              <markPosition x="-192.5066" y="-111.5057" />
            </fiducialMark>
          </fiducialMarkData>
        </bocMark>
        <secondBocMark no="1">
          <markType>NoUse</markType>
          <markName>BOCMARK01</markName>
          <solderType>standard</solderType>
          <effectiveCount count="0" />
          <fiducialMarkData>
            <fiducialMark index="0">
              <markName />
              <markPosition />
            </fiducialMark>
            <fiducialMark index="1">
              <markName />
              <markPosition />
            </fiducialMark>
            <fiducialMark index="2">
              <markName />
              <markPosition />
            </fiducialMark>
          </fiducialMarkData>
        </secondBocMark>
      </circuitData>
    </bocMarkData>
  </machine>
</productionProgram>
